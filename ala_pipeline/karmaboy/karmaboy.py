#! /usr/bin/env hython

from optparse import OptionParser
import os
import re
from typing import Optional, Union
from pathlib import Path
import uuid
import shutil
import sys
from datetime import datetime
try:
    import hou
except ImportError:
    print("This script must be run via 'hython' to interact with Houdini nodes.")
    sys.exit(1)

import shotgun_utils
from houdini_pipeline.hda import ala_context


KARMABOY_ARCHIVE_ROOT = Path('/mnt/ala/mav/20{0}/sandbox/studio1/karmaboy/archive'.format(shotgun_utils.get_project_code()[-2:]))


def main():
    p = OptionParser()
    p.add_option("-s", "--shot", dest='shot', action='store')
    p.add_option("-S", "--step", dest='step', action='store')
    p.add_option("-t", "--task", dest='task', action='store')
    p.add_option("-a", "--asset", dest='asset', action='store')
    p.add_option("-A", "--asset_type", dest='asset_type', action='store')
    p.add_option("-d", "--description", dest='description', action='store')
    p.add_option("-b", "--batch_size", dest='batch_size', action='store')
    p.add_option("-f", "--firstname", dest='firstname', action='store')
    p.add_option("-n", "--lastname", dest='lastname', action='store')
    p.add_option("-o", "--object_version", dest='object_version', action='store')
    
    usage = 'karmaboy.py\n\n'
    usage += '-s, --shot, shot_code eg: pl_060\n'
    usage += '-S, --step, pipeline step eg: animation (required)\n'
    usage += '-t, --task, task: eg: animation (required)\n'
    usage += '-a, --asset, asset_name eg: propTest01\n'
    usage += '-A, --asset_type, asset_type eg: prop\n'
    usage += '-d, --description, a comment for shotgun\n'
    usage += '-f, --firstname, firstname override: eg: John\n'
    usage += '-n, --lastname, lastname override: eg: Doe\n'
    usage += '-o, --object_version version number for render object: eg: 7 (for animation v007)\n'
    usage += '\nexample with long args: render shot pl_060 for animation, with a comment: '
    usage += 'karmaboy.py --shot pl_060 --step animation --task animation'
    usage += '--description "qc check of shot"'
    usage += '\n\nsame example with short args:'
    usage += 'karmaboy.py -s pl_060 -S animation -t animation '
    usage += '-d "qc check of shot"\n'

    p.set_usage(usage)

    # E.g. rez env houdini_pipeline houdini-20.5.445 s126 -- hython karmaboy.py -s lib01_010 -S animation -t animation -d "qc check of shot"
    # E.g. rez env houdini_pipeline houdini-20.5.445 s126 -- hython karmaboy.py -a propTest01 -A prop -S model -t model

    opts, args = p.parse_args()

    if bool(opts.shot) == bool(opts.asset):
        print("Error: Specify exactly one of --shot or --asset.")
        return   
    if (opts.asset and not opts.asset_type) or (opts.asset_type and not opts.asset):
        print("Error: --asset and --asset_type must be supplied together.")
        return
    if not opts.step or not opts.task:
        print("Error: Missing required arguments (--step and --task).")
        return

    is_asset = bool(opts.asset)

    unique_id = uuid.uuid4().hex[:8]
    now = datetime.now()
    timestamp_dir = Path('%s-%s-%s--%s-%s-%s_%s' % (now.year, now.month, now.day, now.hour, now.minute, now.second, unique_id))
    archive_dir = KARMABOY_ARCHIVE_ROOT / timestamp_dir
    archive_dir.mkdir()

    project_code = shotgun_utils.get_project_code()

    if opts.asset:
        source = Path('/mnt/ala/mav/20{0}/sandbox/studio1/karmaboy/karmaboy_modelling_nolookfile.hipnc'.format(project_code[-2:]))
    else:
        source = Path('/mnt/ala/mav/20{0}/sandbox/studio1/karmaboy/karmaboy_nolookfile.hipnc'.format(project_code[-2:]))
    dest = archive_dir / "karmaboy.hipnc"

    shutil.copy(source, dest)
    dest.chmod(0o666)

    print(f"Loading generated scene file: {dest}")
    hou.hipFile.load(str(dest), suppress_save_prompt=True, ignore_load_warnings=True)

    if is_asset:
        # Updates the HDA by reloading the HDA file and changing the node to the latest version
        hda_path = "/mnt/ala/mav/2026/jobs/{0}/library/hda_templates/ala_modelling_template.hdanc".format(project_code)
        hou.hda.reloadFile(hda_path)

        template_node = hou.node("/obj/ala_modelling_template1")
        if not template_node:
            raise RuntimeError("Missing node: /obj/ala_modelling_template1")

        latest_definition = template_node.type().namespaceOrder()[0]
        print("Latest definition: ", latest_definition)
        template_node = template_node.changeNodeType(latest_definition, keep_network_contents=False)

        template_node.matchCurrentDefinition()
        template_node.allowEditingOfContents()

        hou.hipFile.save()

        top_net = hou.node('/obj/ala_modelling_template1/topnet1') 
        scheduler_node = hou.node('/obj/ala_modelling_template1/topnet1/alatractorscheduler1')
        context_node = hou.node('/obj/ala_modelling_template1/alacontext1')
        context_wedge_node = hou.node('/obj/ala_modelling_template1/topnet1/contextwedge1')
    else:
        top_net = hou.node('/obj/topnet1') 
        scheduler_node = hou.node('/obj/topnet1/alatractorscheduler1')
        context_node = hou.node('/obj/alacontext1')
        context_wedge_node = hou.node('/obj/topnet1/contextwedge1')

    required_nodes = {
        "top_net": top_net,
        "scheduler_node": scheduler_node,
        "context_node": context_node,
        "context_wedge_node": context_wedge_node,
    }

    for name, node in required_nodes.items():
        if not node:
            raise RuntimeError(f"Missing node: {name}")

    sg_data = get_shotgrid_env_data(
        opts.step, 
        opts.task, 
        archive_dir, 
        opts.description, 
        opts.object_version, 
        shot_name = opts.shot if not is_asset else None,
        asset_name = opts.asset if is_asset else None, 
        asset_type = opts.asset_type, 
        first_name = opts.firstname, 
        last_name = opts.lastname
    )
    print("SG Data:", sg_data)
    create_shotgrid_env_data(sg_data)

    if opts.batch_size: 
        scheduler_node.parm('maxactive').set(int(opts.batch_size))   

    # Update project data
    ala_context.sg_update_clicked({'node': context_wedge_node})
    context_wedge_node.dirtyWorkItems(remove_outputs=True)
    context_wedge_node.cookWorkItems(block=True)

    # Add context of entity
    if is_asset:
        context_wedge_node.parm("wildcard").set(opts.asset)
        ala_context.add_wildcard_clicked({'node': context_wedge_node}, ctx_type = "Asset")
    else:
        context_wedge_node.parm("wildcard").set(opts.shot)
        ala_context.add_wildcard_clicked({'node': context_wedge_node})

    # Generate variables related to context
    if is_asset:
        context_node.parm("ctx_menu").set(opts.asset)
        context_wedge_node.parm("comment0").set(sg_data["description"])
    else:
        context_node.parm("ctx_menu").set(opts.shot)
    ala_context.ctx_refresh_clicked({'node': context_node})

    if is_asset:
        # Set the parameters of the turret node and reload it
        turret_node = hou.node("/obj/ala_modelling_template1/lopnet1/turretread1")
        turret_node.parm("project").set(project_code)
        turret_node.parm("asset").set(opts.asset)
        turret_node.parm("cache_type").set("asset")

        reload_module = turret_node.hdaModule()
        reload_module.update_uri(kwargs={"node": turret_node})

        set_correct_modelling_template_paths()

    hou.hipFile.save()

    if is_asset:
        submit_node = hou.node('/obj/ala_modelling_template1/topnet1/submit_for_review')
        submit_node.dirtyWorkItems(remove_outputs=True)
        submit_node.cookWorkItems(block=True)
    else:
        top_net.dirtyWorkItems(remove_outputs=True)
        top_net.cookWorkItems(block=True)

def get_shotgrid_env_data(step_name: str, task_name: str, archive_dir: str, description: str, render_version: str, 
                          shot_name: Optional[str] = None, asset_name: Optional[str] = None, asset_type: Optional[str] = None, 
                          first_name: Optional[str] = None, last_name: Optional[str] = None, render_test: Optional[str] = False):
    is_asset = bool(asset_name)

    tk = shotgun_utils.get_tk()
    project_code = shotgun_utils.get_project_code()
    project = tk.shotgun.find_one('Project', [['tank_name', 'is', project_code]], ['id', 'name'])
    project_name = project["name"]

    if is_asset:
        sequence_name = ""
    else:
        sequence_name = shot_name.split("_")[0]

    if not first_name or not last_name:
        crewname = os.getenv("CREWNAME")
        if not crewname or "." not in crewname:
            raise RuntimeError("Invalid CREWNAME environment variable")
        first_name, last_name = crewname.split(".", 1)

    user_name = f"{first_name}.{last_name}"

    if render_test:
        render_path = archive_dir / "renders"
        render_path.mkdir()
    else:
        tk = shotgun_utils.get_tk()
        if is_asset:
            template = "houdini_wip_asset_renders_root"
        else:
            template = "houdini_wip_shot_renders"

        template_path = tk.templates[template]

        fields = {}
        fields['HumanUser.firstname'] = first_name
        fields['HumanUser.lastname'] = last_name
        if is_asset:
            fields['Asset'] = asset_name
            fields['asset_type'] = asset_type
        else:
            fields['Shot'] = shot_name
            fields['Sequence'] = sequence_name

        fields['Step'] = step_name
        fields['Task'] = task_name

        render_path = Path(template_path.apply_fields(fields))
    
    karmaboy_path = render_path / "karmaboy"

    version_pattern = re.compile(r'^v(\d{3})$')

    if not karmaboy_path.exists():
       karmaboy_path.mkdir(parents=True)

    if render_version:
        padded_render_version = f"v{int(render_version):03d}"
        version_path = karmaboy_path / padded_render_version
        try:
            version_path.mkdir()
        except FileExistsError:
            raise RuntimeError(f"Render version already exists: {version_path}")
    else:
        latest = 0
        for item in karmaboy_path.iterdir():
            m = version_pattern.match(item.name)
            if m and item.is_dir():
                latest = max(latest, int(m.group(1)))

        next_version = latest + 1
        while True:
            padded_render_version = f"v{next_version:03d}"
            version_path = karmaboy_path / padded_render_version
            try:
                version_path.mkdir()
                break
            except FileExistsError:
                next_version += 1

    if description:
        full_description = description
    else:
        full_description = f"Automatic {task_name} {padded_render_version} render for {first_name} {last_name} - Automatic render by karmaboy"

    return {
        "context": "ASSET" if is_asset else "SHOT",
        "project": project_name,
        "shot": shot_name if not is_asset else "",
        "asset": asset_name if is_asset else "",
        "asset_type": asset_type if is_asset else "",
        "sequence": sequence_name,
        "step": step_name,
        "task": task_name,
        "user_name": user_name,
        "render_path": str(render_path),
        "render_version": str(padded_render_version),
        "unpadded_render_version": int(render_version) if render_version else next_version,
        "description": full_description
    }

def create_shotgrid_env_data(sg_data: dict[str, Union[str, int]]):
    hou.putenv("SG_CONTEXT", sg_data["context"])
    hou.putenv("SG_SEQUENCE", sg_data["sequence"])
    hou.putenv("SG_TASK", sg_data["task"])
    hou.putenv("SG_STEP", sg_data["step"])
    hou.putenv("SG_DESCRIPTION", sg_data["description"])
    hou.putenv("SG_VERSION", str(sg_data["unpadded_render_version"]))
    hou.putenv("SG_PROJECT", sg_data["project"])

    if sg_data["asset"]:
        hou.putenv("SG_ASSET", sg_data["asset"])
        hou.setContextOption("ASSET", sg_data["asset"]) 
        hou.setContextOption("CONTEXT", sg_data["asset"]) 
    else:
        hou.putenv("SG_SHOT", sg_data["shot"])
        hou.setContextOption("CONTEXT", sg_data["shot"]) 

    hou.setContextOption("PROJECT", shotgun_utils.get_project_code())
    hou.setContextOption("RENDER_PATH", sg_data["render_path"])
    hou.setContextOption("RENDER_VERSION", sg_data["render_version"])

def set_correct_modelling_template_paths():
    copnet = hou.node("/obj/ala_modelling_template1/topnet1/copnet1")

    for pass_type in ["ao", "grey", "uv", "wireframe"]:
        pass_node = hou.node(f"/obj/ala_modelling_template1/lopnet1/renderOut_{pass_type}")
        pass_node.parm("basename").set(f"karmaboy_{pass_type}_`@RENDER_VERSION`")
        pass_node.parm("basedir").set("`@RENDER_PATH`/$HIPNAME/`@RENDER_VERSION`/exr")

        pass_node.parm("enableversion").set(True)
        pass_node.parm("version").deleteAllKeyframes()
        pass_node.parm("version").set(1)
        pass_node.parm("enableversion").set(False)

        copnet.node(pass_type).parm("filename").set(f"`@RENDER_PATH`/$HIPNAME/`@RENDER_VERSION`/exr/karmaboy_{pass_type}_`@RENDER_VERSION`/`@CONTEXT`_karmaboy_{pass_type}_`@RENDER_VERSION`.$F4.exr")

    copnet.node("rop_image1").parm("copoutput").set("`@RENDER_PATH`/$HIPNAME/`@RENDER_VERSION`/exr/karmaboy_contact_sheet_`@RENDER_VERSION`/`@CONTEXT`_karmaboy_contact_sheet_`@RENDER_VERSION`.$F4.exr")

    ocio_node = hou.node('/obj/ala_modelling_template1/topnet1/ala_ocioconv1')
    ocio_node.parm("copoutput").set("`@RENDER_PATH`/$HIPNAME/`@RENDER_VERSION`/jpg/`@CONTEXT`_karmaboy_primary_`@RENDER_VERSION`.$F4.jpg") 

    submit_node = hou.node('/obj/ala_modelling_template1/topnet1/submit_for_review')
    submit_node.parm("movie_path").set("`@RENDER_PATH`/$HIPNAME/`@RENDER_VERSION`/mov") 

if "__main__" == __name__:
    main()