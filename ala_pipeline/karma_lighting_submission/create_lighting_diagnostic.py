import os
import glob
import re
from pathlib import Path
from optparse import OptionParser
import nuke
import sgtk

import shotgun_utils
import lightingDiagnostics
from nuke_pipeline import artist_api


def main():
    p = OptionParser()
    p.add_option("-s", "--shot", dest='shot', action='store')
    p.add_option("-f", "--frames", dest='frames', action='store')
    p.add_option("-d", "--description", dest='description', action='store')
    
    usage = 'create_lighting_diagnostic.py usage:\n\n'
    usage += '-s --shot shot_code eg: pl_060 (required)\n'
    usage += '-f --frames frame total eg: 1-100 (required)\n'
    usage += '-d --description a comment for shotgun\n'
    usage += 'example: create_lighting_diagnostic.py -v 5 -s pl_060 -d "qc check of shot"\n'
    
    # E.g. rez env s126 nuke_pipeline nuke -- bash -c '$NUKE_BIN -t -- create_lighting_diagnostic.py -f "1001-1100" -s tst04_070'

    opts, args = p.parse_args()

    if not opts.shot or not opts.frames:
        p.error("Missing required arguments (-s, -f).")
        
    tk = shotgun_utils.get_tk()

    if not sgtk.platform.current_engine() and not os.environ.get('SHOTGUN_INIT_RUN') and os.environ.get("SHOTGUN_PROJECT"):
        print("Trying to bootstrap tk-nuke")
        shotgun_utils.auth.bootstrap_engine_from_project_name(os.environ["SHOTGUN_PROJECT"], 'tk-nuke')

    file_path, version = create_file(tk, opts.shot)

    output_path = get_output_path(tk, opts.shot, version)
    call_lighting_diagnostic(output_path)

    nuke.scriptSave(file_path)

    launch_review_farm_job(opts.frames)

def create_file(tk, shot):
    root_template = "wip_shot_task_root"
    root_template_path = tk.templates[root_template]

    first_name = os.getenv('CREWNAME').split(".")[0]
    last_name = os.getenv('CREWNAME').split(".")[1]

    fields = {}
    fields['HumanUser.firstname'] = first_name
    fields['HumanUser.lastname'] = last_name
    fields['Shot'] = shot
    fields['Sequence'] = shot.split("_")[0]
    fields['Step'] = "light"
    fields['Task'] = "qcRender"

    base_path = root_template_path.apply_fields(fields)

    latest_version = get_latest_light_qcrender(base_path) + 1
    fields['version'] = latest_version

    template = "nuke_wip_shot_build_path"
    template_path = tk.templates[template]
    file_path = template_path.apply_fields(fields)

    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    nuke.scriptSaveAs(file_path)

    print("Lighting Diagnostic File Path: ", file_path)

    return (file_path, latest_version)

def get_latest_light_qcrender(sequence_path):
    pattern = os.path.join(
        sequence_path,
        "*",
        "nuke",
        "build",
        "*_light_qcRender.v*.nk",
    )

    files = glob.glob(pattern)

    latest_file = max(files, key=get_version_num, default=None)

    return get_version_num(latest_file) if latest_file else 0

def get_version_num(path):
    return int(re.search(r'\.v(\d+)\.nk$', path).group(1))

def call_lighting_diagnostic(output_path):
    plate_dir = sgtk.platform.current_engine().context.entity_locations[0] + f'/departments/comp'
    if Path(plate_dir).exists:
        has_plate = any(folder.is_dir() and "plate" in folder.name.lower() for folder in Path(plate_dir).iterdir())
    else:
        has_plate = False
 
    if has_plate:
        print("Building VFX lighting diagnostics")
        lightingDiagnostics.vfxLightingDiagnostics()
    else:
        print("Building CG lighting diagnostics")
        lightingDiagnostics.cgLightingDiagnostics()

    node = nuke.allNodes("WriteTank")[0]
    node.knob("cached_path").setValue(output_path)
    node.knob("tk_cached_proxy_path").setValue(output_path)

def get_output_path(tk, shot, version):
    template = "publish_shot_task_review_version_root"
    template_path = tk.templates[template]

    fields = {}
    fields['Shot'] = shot
    fields['Sequence'] = shot.split("_")[0]
    fields['Step'] = "light"
    fields['Task'] = "qcRender"
    fields['version'] = version

    file_path = template_path.apply_fields(fields)
    path = str(Path(file_path) / "exr" / f"{shot}_light_qcRender_output1.v{version:03}.%04d.exr")

    return path

def launch_review_farm_job(frames):
    for node in nuke.allNodes("WriteTank"):
        if node.knob("colorspace").value() == "linear" or node.knob("colorspace").value() == "default (linear)":
            node.knob("colorspace").setValue("scene_linear")

    write_tank_nodes = [node for node in nuke.allNodes() if node.Class() == "WriteTank"]
    node = write_tank_nodes[0] if write_tank_nodes else None

    artist_api.farm_render(node.name(), frames=frames, sg_upload=True)

if __name__ == "__main__":
    main()