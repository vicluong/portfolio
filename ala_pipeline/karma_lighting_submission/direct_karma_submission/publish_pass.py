from optparse import OptionParser
import os
import sys
import ast
import re
try:
    import hou
except ImportError:
    print("This script must be run via 'hython' to interact with Houdini nodes.")
    sys.exit(1)

import shotgun_utils
import houdini_pipeline.shotgun as hpshotgun


def main():
    p = OptionParser()
    p.add_option("-s", "--submissionshot", dest='submission_shot', action='store')
    p.add_option("-p", "--passtype", dest='pass_type', action='store')
    p.add_option("-P", "--pubfolder", dest='pubfolder', action='store')
    p.add_option("-f", "--framelist", dest='framelist', action='store')
    p.add_option("-F", "--framerange", dest='framerange', action='store')
    p.add_option("-v", "--sourceversion", dest='sourceversion', action='store')
    p.add_option("-c", "--comment", dest='comment', action='store')
    p.add_option("-H", "--hipfile", dest='hipfile', action='store')
    p.add_option("-d", "--draftdeletion", dest='draftdeletion', action='store')

    opts, args = p.parse_args()

    print(opts)

    if opts.hipfile:
        hou.hipFile.load(opts.hipfile, suppress_save_prompt=True, ignore_load_warnings=True)

    submission_shot = opts.submission_shot
    pass_type = opts.pass_type
    pubfolder = opts.pubfolder
    framelist = ast.literal_eval(opts.framelist)
    framerange = ast.literal_eval(opts.framerange)
    sourceversion = opts.sourceversion if opts.sourceversion else None
    comment = opts.comment if opts.comment else ""
    draft_deletion = True if opts.draftdeletion == "True" else False

    context_type = "Shot"
    asset = ""
    project = shotgun_utils.get_project_code()
    step = "light"
    task = "lighting"
    shot = submission_shot
    seq = submission_shot.split("_")[0]
    render_pass = pass_type
    dry_run = False

    render_file = f"{pubfolder}/{pass_type}/{submission_shot}_{pass_type}_$F4.exr"

    if render_file == None:
        raise FileNotFoundError("Can't find Render files to publish")
    if not render_file.endswith('.exr'):
        raise ValueError("Files don't appear to be an EXR Render: {}".format(render_file))

    print(f"Pubfile renders: {render_file}")
    
    # Build list of all files to publish: primary + lightgroup splits
    publish_items = [{'filepath': render_file, 'lightgroup': 'primary'}]
    
    rp_node = hou.node(f'/obj/lopnet1/karmarenderproducts_{render_pass}')
    if rp_node:
        num_products = rp_node.parm('products').eval()
        for i in range(num_products):
            lg = rp_node.parm(f'primname_{i}').eval()
            filepath = rp_node.parm(f'productName_{i}').eval()
            if not lg or not filepath:
                continue
            filepath = re.sub(r'\.\d{4}\.exr$', '.%04d.exr', filepath)
            publish_items.append({'filepath': filepath, 'lightgroup': lg})
    else:
        print(f"No karmarenderproducts_{render_pass} node found, skipping lightgroup splits")

    # Publish all items
    result = None
    print("Publish_items", publish_items)
    for item in publish_items:
        print(f"Publishing: {item['lightgroup']} -> {item['filepath']}")
        result = hpshotgun.publish_file(item['filepath'],
                    comment, context_type, asset,
                    project, task, step, seq, shot,
                    render_pass=render_pass,
                    frange=framerange,
                    flist=framelist,
                    version_number=sourceversion,
                    lightgroup=item['lightgroup'],
                    dry_run=dry_run,
                    draft_deletion=draft_deletion)
        
        print("Publish Complete!")
        if result['success'] == False:
            raise Exception(result['message'])
        
        print(f"Published: {item['lightgroup']} -> {result.get('pub_path', 'no path')}")


if __name__ == "__main__":
    main()
