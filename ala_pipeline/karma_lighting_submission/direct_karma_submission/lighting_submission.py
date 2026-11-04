import os
import sys
import subprocess
import time
import uuid
import re
from typing import Optional
from pathlib import Path
import hou
from datetime import datetime, timedelta
import calendar
import tractor.api.author as author

from houdini_pipeline.hda import ala_context
from houdini_pipeline.direct_karma_submission import farm_submitter_helpers as fsh
import houdini_pipeline.shotgun as hpshotgun
import shotgun_utils


HOUDINI_PYTHON_PATH = "$REZ_HOUDINI_PIPELINE_ROOT/python/houdini_pipeline/direct_karma_submission"

# ------------------------------------ Main ------------------------------------

def submit_lighting_job():
    samples_per_pixel = hou.node("/obj/lopnet1/bty").parm("samplesperpixel").eval()
    if hou.node("/obj/lopnet1/bty").parm("samplesperpixel").eval() >= 100:
        if not hou.ui.displayConfirmation(f"Bty Pixel Samples is set to {samples_per_pixel}.\n\nAre you sure you want to submit this job?", 
                                      title="Confirm Submit"):
            return

    hou.hipFile.save()

    submitter_node = hou.node("/obj/lopnet1/Farm_Submitter")

    original_hip_file = hou.hipFile.path()

    if submitter_node.parm("multi_shot").eval() == True:
        valid_shots = fsh.get_valid_shots()
        
        checked_shots = []
        for shot in valid_shots:
            parm = submitter_node.parm(f"{shot}_checkbox")
            if parm is not None and parm.eval():
                checked_shots.append(shot)
        shots = checked_shots

    else:
        shots = [submitter_node.parm("submission_shot").evalAsString()]

    draft_deletion = bool(submitter_node.parm("draft_deletion").eval())
    comment = submitter_node.parm("comment").evalAsString()

    job_version = int(hou.getenv("SG_VERSION"))

    try:
        for submission_shot in shots:
        
            save_latest_context_version(submission_shot)

            submitter_node = hou.node("/obj/lopnet1/Farm_Submitter")
            submitter_node.parm("submission_shot").set(submission_shot)

            pass_types = filter_submission_and_applicability(submission_shot)

            path_creator_node = hou.node("/obj/lopnet1/rop_folder_path_creator")
            path_creator_node.cook(force=True)
            wip_folder = path_creator_node.parm("folder_path").evalAsString()

            # Save the context change into the versioned hip
            hou.hipFile.save()   

            env_vars = turret_cache_gen_cook(submission_shot)
            source_version = publish_hip(submission_shot, comment)

            framelist, framerange = get_frames()

            build_job(submission_shot, pass_types, wip_folder, source_version, env_vars, 
                      framelist, framerange, comment, draft_deletion, job_version)

    finally:
        hou.hipFile.load(original_hip_file, suppress_save_prompt=True, ignore_load_warnings=True)

        context_node = hou.node("/obj/alacontext1")
        original_ctx = context_node.parm("ctx_menu").evalAsString()
        context_node.parm("ctx_menu").set(original_ctx)
        context_node.parm("context").set(original_ctx)
        ala_context.ctx_refresh_clicked({'node': context_node})

# ------------------------------------ Main ------------------------------------

# --------------------------------- Versioning ---------------------------------

def save_latest_context_version(submission_shot: str) -> None:
    tk = shotgun_utils.get_tk()
    root_template = "wip_shot_task_root"
    root_template_path = tk.templates[root_template]

    fields = {}
    fields['HumanUser.firstname'] = hou.getenv("SG_USER").split(".")[0]
    fields['HumanUser.lastname'] = hou.getenv("SG_USER").split(".")[1]
    fields['Shot'] = submission_shot
    fields['Sequence'] = submission_shot.split("_")[0]
    fields['Step'] = "light"
    fields['Task'] = "lighting"

    base_path = root_template_path.apply_fields(fields)

    latest_version = get_latest_lighting_version(base_path) + 1
    fields['version'] = latest_version

    template = "houdini_wip_shot_build_path"
    template_path = tk.templates[template]
    file_path = template_path.apply_fields(fields)

    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    hou.hipFile.save(file_name=file_path)

def get_latest_lighting_version(sequence_path):
    files = [
        str(p)
        for p in Path(sequence_path).glob("*/houdini/build/*_light_lighting.v*.*")
        if p.suffix in {".hip", ".hipnc"}
    ]

    latest_file = max(files, key=get_version_num, default=None)

    return get_version_num(latest_file) if latest_file else 0

def get_version_num(path):
    return int(re.search(r'\.v(\d+)\.hip(?:nc)?$', path).group(1))

# --------------------------------- Versioning ---------------------------------

# ----------------- Filtering by submission and applicability ------------------

def filter_submission_and_applicability(submission_shot: str) -> Optional[list[str]]:
    parent_node = hou.node("/obj/lopnet1")

    # Change context to submission shot
    context_node = hou.node("/obj/alacontext1")
    context_node.parm("ctx_menu").set(submission_shot)
    context_node.parm("context").set(submission_shot)
    ala_context.ctx_refresh_clicked({'node': context_node})

    applicability_nodes = [child for child in parent_node.children() if "applicability_" in child.name()]

    valid_pass_types = []
    for node in applicability_nodes:
        valid_pass = get_valid_pass(node, submission_shot)
        if valid_pass:
            valid_pass_types.append(valid_pass)

    if not valid_pass_types:
        raise ValueError("Shot selected had no valid pass types.")

    checked_pass_types = []
    submitter_node = hou.node("/obj/lopnet1/Farm_Submitter")

    if submitter_node.parm("multi_shot").eval():
        checked_pass_types = valid_pass_types
    else:
        for pass_type in valid_pass_types:
                parm = submitter_node.parm(f"{pass_type}_checkbox")
                if parm is not None and parm.eval():
                    checked_pass_types.append(pass_type)

    return checked_pass_types

def get_valid_pass(applicability_node: hou.node, submission_shot:str) -> str:
    if fsh.is_shot_applicable(applicability_node, submission_shot):
        return applicability_node.name().split("_", 1)[1]
    return None

def turret_cache_gen_cook(submission_shot: str) -> dict:
    shot = submission_shot
    seq = submission_shot.split("_")[0]
    context = shot

    env_vars = {}

    print("\nInit turret cache gen for shot %s:\n" % shot)
    
    tk = shotgun_utils.get_tk()
    template = 'publish_shot_description_path'
    template_path = tk.templates[template]
    fields = {}
    fields['Shot'] = shot
    fields['Sequence'] = seq

    publishes = tk.paths_from_template(template_path, fields)
    publishes.sort()

    archive_usd_cache = ""

    # TODO: get every usd input that is being used in this render and collate into a comma-separated list, 
    # should allow for more flexible resolving if multiple usd/turretreads are used with references
    if len(publishes) == 0:
        print(f"No publishes found for {context}. Skipping turret cache gen.")
        return env_vars
    
    usd = publishes[-1]
    
    session_id = hou.getenv('session_id',str(uuid.uuid4()))
    
    proj_file = hou.hipFile.path()
    project_pardir = os.path.abspath(os.path.join(proj_file, os.path.pardir))
    archive_dir = os.path.join(project_pardir, '.archive')
    turret_archive_time_dir = os.path.join(archive_dir, str(time.time()))
    turret_archive_root = os.path.join(turret_archive_time_dir, str(context))
    archive_usd_cache = turret_archive_root + '/usd_%s.turretcache' % session_id

    try:
        os.makedirs(turret_archive_root)
    except OSError:
        pass
    
    asset_time = hou.getenv('USD_ASSET_TIME',None)
    if(asset_time == None):
        user_dt = datetime.now()
        timestamp = calendar.timegm(user_dt.timetuple())
        local_dt = datetime.fromtimestamp(timestamp)
        assert user_dt.resolution >= timedelta(microseconds=1)
        local_dt = local_dt.replace(microsecond=user_dt.microsecond)
        asset_time = time.mktime(local_dt.timetuple())
        env_vars["USD_ASSET_TIME"] = str(asset_time)

    cmd = ['turret_cache_gen_init']
    cmd += ['--usd', str(usd)]
    cmd += ['--session_id', str(session_id)]
    cmd += ['--destination', str(turret_archive_root)]
    cmd += ['--asset_time', str(asset_time)]

    print("Turret cache gen cmd:")
    print(' '.join(cmd))

    print("\nStarting rez env for turret cache gen\n")
    proc = subprocess.Popen(' '.join(cmd), stdout=subprocess.PIPE, shell=True)
    
    while True:
        nextline = proc.stdout.readline().decode('utf-8')
        if nextline == '' and proc.poll() is not None:
            break
        sys.stdout.write(nextline)
        sys.stdout.flush()
        
    output = proc.communicate()[0]
    exit_code = proc.returncode

    if exit_code != 0:
        print(output)
    print("Finished turret cache gen\n")

    #Keeping this as 1 incase extra USD is brought in so it can be resolved 
    env_vars["TURRET_USD_ALLOW_LIVE_RESOLVES"] = str(1)
    env_vars["TURRET_USD_CACHE_TO_DISK"] = str(0)
    env_vars["TURRET_USD_CACHE_LOCATION"] = str(archive_usd_cache)

    print("TURRET_USD_CACHE_LOCATION: " + str(archive_usd_cache))
    print("Updated work item attrs\n")

    return env_vars

# ----------------- Filtering by submission and applicability ------------------

# ----------- Creating jobs for rendering, publishing and reviewing ------------

def publish_hip(submission_shot: str, comment: str) -> int:
    context_type = "Shot"
    asset = ""
    project = shotgun_utils.get_project_code()
    step = "light"
    task = "lighting"
    seq = submission_shot.split("_")[0]
    shot = submission_shot
    source_version = None
    dry_run = False

    result = hpshotgun.publish_file(hou.hipFile.path(), comment, context_type, asset, project, task, 
                                    step, seq, shot, version_number=source_version, dry_run=dry_run)

    if result['success'] == False:
        raise Exception(result['message'])
    else:
        source_version = result['version_number']

    return source_version

def get_frames() -> tuple[list[int], list[int]]:
    farm_submitter_node = hou.node("/obj/lopnet1/Farm_Submitter")
    frames_type = farm_submitter_node.parm("shotrange").evalAsString()
    shot_start = int(hou.text.expandString("`@SHOTSTART`"))
    shot_end = int(hou.text.expandString("`@SHOTEND`"))

    framelist = None
    framerange = None

    if frames_type == "FullRange":
        framerange = [shot_start, shot_end, 1]
    elif frames_type == "Step5":
        framerange = [shot_start, shot_end, 5]
    elif frames_type == "Step10":
        framerange = [shot_start, shot_end, 10]
    elif frames_type == "FirstMiddleLast":
        shot_middle = (shot_start + shot_end) // 2
        framelist = [shot_start, shot_middle, shot_end]
    elif frames_type == "CustomRange":
        custom_start = int(farm_submitter_node.parm("custom_rangex").evalAsString())
        custom_end = int(farm_submitter_node.parm("custom_rangey").evalAsString())
        custom_interval = int(farm_submitter_node.parm("custom_interval").evalAsString())
        framerange = [custom_start, custom_end, custom_interval]
    else:
        framerange = [shot_start, shot_end, 1]

    return framelist, framerange

def build_job(submission_shot: str, pass_types: Optional[list[str]], wip_folder: str, 
              source_version: int, env_vars: dict[str, str], framelist: Optional[list[int]], 
              framerange: Optional[list[int]], comment: str, draft_deletion: bool, job_version: int) -> None:
    job = create_job(env_vars, submission_shot, job_version, comment, framelist, framerange)

    create_passes_task(job, submission_shot, pass_types, wip_folder, source_version, 
                       framelist, framerange, comment, draft_deletion)
    
    job_id = job.spool()
    print("Job Spooled: Id - ", job_id)

def create_job(env_vars: dict[str, str], submission_shot: str, job_version: int, 
               comment: str, framelist: Optional[list[int]], framerange: Optional[list[int]]) -> author.Job:
    user = hou.getenv("SG_USER")
    scheduler = hou.node("/obj/topnet1/alatractorscheduler1")

    job = author.Job(
        title=f"{user} {submission_shot} v{job_version:03} Light Job"
    )

    envkey = ['rez-pkgs=houdini_pipeline houdini s126']
    for key, value in env_vars.items():
        envkey += [f"setenv {key}={value}"]

    orig_tractor_tier = scheduler.parm("tractor_tier").evalAsString()

    if framelist:
        frames = len(framelist)
    else:
        frames = len(range(framerange[0], framerange[1] + 1, framerange[2]))

    if frames < 10:
        tier = "rush"
    else:
        tier = "default"

    scheduler.parm("tractor_tier").set(tier)

    job.tier = scheduler.parm("tractor_tier").evalAsString()
    job.priority = float(scheduler.parm("tractor_priority").eval())
    job.service = 'bash'
    job.envkey = envkey
    job.comment = comment
    job.metadata = scheduler.parm("tractor_metadata").evalAsString()

    scheduler.parm("tractor_tier").set(orig_tractor_tier)

    return job

def create_passes_task(job: str, submission_shot: str, pass_types: Optional[list[str]], 
                       wip_folder: str, source_version: int, framelist: Optional[list[int]], 
                       framerange: Optional[list[int]], comment: str, draft_deletion: bool) -> None:
    if framelist:
        frames = framelist
    else:
        frames = []
        for f in range(framerange[0], framerange[1]+1, framerange[2]):
            frames.append(f)

    review_tasks = create_review_tasks(submission_shot)

    for pass_type in pass_types:
        frame_tasks = create_frame_tasks(submission_shot, pass_type, wip_folder, frames)
        publish_pass_task = create_publish_task(submission_shot, pass_type, source_version, wip_folder, 
                                                framelist, framerange, comment, draft_deletion)

        for frame_task in frame_tasks:
            job.addChild(frame_task)
            publish_pass_task.addChild(author.Instance(title=f"{frame_task.title}"))
        job.addChild(publish_pass_task)

        for review_task in review_tasks:
            review_task.addChild(author.Instance(title=f"{publish_pass_task.title}"))

    for review_task in review_tasks:
        job.addChild(review_task)

def create_frame_tasks(submission_shot: str, pass_type: str, 
                                wip_folder: str, frames: list[str]) -> list[author.Task]:
    frame_tasks = []

    for frame in frames:
        output_path = f"{wip_folder}/{pass_type}/{submission_shot}_{pass_type}_{frame}.exr"
        frame_task = author.Task(title=f"Pass: {pass_type} - Frame: {frame}")

        render_script = f"{HOUDINI_PYTHON_PATH}/karma_render_frame.sh"

        # Pass %j, %t and %n through to represent the job_id, task_id and number of slots
        tractor_cmd = author.Command(
            argv=[
                render_script,
                hou.hipFile.path(),
                f"/obj/lopnet1/{pass_type}",
                output_path,
                str(frame),
                "%j",
                "%t",
                "%n",
            ]
        )
        add_command_attributes(tractor_cmd)

        frame_task.addCommand(tractor_cmd)
        frame_tasks.append(frame_task)

    return frame_tasks

def create_publish_task(submission_shot: str, pass_type: str, source_version: int, 
                        wip_folder: str, framelist: Optional[list[int]], framerange: Optional[list[int]], 
                        comment: str, draft_deletion: bool) -> author.Task:
    hipfile = hou.hipFile.name()
    publish_pass_path = f"{HOUDINI_PYTHON_PATH}/publish_pass.py"

    publish_pass_task = author.Task(title=f"Publish Pass: {pass_type}")

    publish_cmd = [
        "hython",
        f"{publish_pass_path}",
        "-s", f"{submission_shot}",
        "-p", f"{pass_type}",
        "-P", f"{wip_folder}",
        "-f", f"{framelist}",
        "-F", f"{framerange}",
        "-v", f"{source_version}",
        "-H", f"{hipfile}",
        "-d", f"{draft_deletion}"
    ]

    if comment and comment.strip():
        publish_cmd.extend(["--comment", comment])

    tractor_cmd = author.Command(
        argv = publish_cmd
    )
    add_command_attributes(tractor_cmd, 4, 4, False)
    
    publish_pass_task.addCommand(tractor_cmd)

    return publish_pass_task

def create_review_tasks(submission_shot: str) -> Optional[list[author.Task]]:
    diagnostic = hou.node("/obj/lopnet1/Farm_Submitter").parm("review").eval()
    bash_comp = hou.node("/obj/lopnet1/Farm_Submitter").parm("bash_comp").eval()

    shot_start = hou.text.expandString("`@SHOTSTART`")
    shot_end = hou.text.expandString("`@SHOTEND`")
    frame_range = f"{shot_start}-{shot_end}"

    review_path = f"{HOUDINI_PYTHON_PATH}/create_review_job.py"

    review_tasks = []

    if diagnostic:
        diagnostic_task = author.Task(title=f"Diagnostic Review Job: {submission_shot}")

        diagnostic_cmd = author.Command(
            argv = [
                "python",
                f"{review_path}",
                "-s", f"{submission_shot}",
                "-d", f"{diagnostic}",
                "-f", f"{frame_range}"
            ]
        )
        add_command_attributes(diagnostic_cmd, 4, 4, False)
        # Using thylacine results in json type error
        diagnostic_cmd.service = "!thylacine"

        diagnostic_task.addCommand(diagnostic_cmd)
        
        review_tasks.append(diagnostic_task)

    if bash_comp:
        bash_comp_task = author.Task(title=f"Bash Comp: {submission_shot}")

        bash_comp_cmd = author.Command(
            argv = [
                "python",
                f"{review_path}",
                "-s", f"{submission_shot}",
                "-B", f"{bash_comp}",
                "-f", f"{frame_range}"
            ]
        )

        add_command_attributes(bash_comp_cmd, 4, 4, False)
        # Using thylacine results in json type error
        bash_comp_cmd.service = "!thylacine"

        bash_comp_task.addCommand(bash_comp_cmd)

        review_tasks.append(bash_comp_task)

    return review_tasks

def add_command_attributes(command: author.Command, least_slots: int = 0, 
                           most_slots: int = 0, tags: bool = True) -> author.Command:
    scheduler = hou.node("/obj/topnet1/alatractorscheduler1")

    if least_slots > 0:
        command.atleast = least_slots
    else:
        command.atleast = int(scheduler.parm("tractor_atleast").eval())

    if scheduler.parm("tractor_useatmost").eval():
        if most_slots > 0:
            command.atmost = most_slots
        else:
            command.atmost = int(scheduler.parm("tractor_atmost").eval())

    if tags:
        command.tags = scheduler.parm("tractor_limittags").evalAsString().replace(",", " ").split()
        command.service = scheduler.parm("tractor_servicekeys").evalAsString()
    command.envkey = [scheduler.parm("tractor_envkeys").evalAsString()]

    return command


if __name__ == "__main__":
    submit_lighting_job()