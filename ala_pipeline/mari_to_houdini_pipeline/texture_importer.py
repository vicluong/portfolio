import hou

def update_textures(kwargs=None):
    if kwargs == None:
        node = hou.pwd()
    else:
        node = kwargs['node']
    
    if hou.expandString('$SG_USER'):
        first_name = hou.expandString('$SG_USER').split('.')[0]
        last_name = hou.expandString('$SG_USER').split('.')[1]
    else:
        import os
        if os.getenv('CREWNAME'):
            first_name = os.getenv('CREWNAME').split(".")[0]
            last_name = os.getenv('CREWNAME').split(".")[1]
        
    args = {}
    args['project'] = node.parm("project").unexpandedString()
    args['version'] = node.parm("version").eval()
    args['asset_type'] = node.parm("asset_type").unexpandedString()
    args['asset'] = node.parm("asset").eval()
    args['first_name'] = first_name
    args['last_name'] = last_name
    # args['published'] = node.parm("published").eval()
    
    texture_paths_info, version_folder, version = get_texture_paths(**args)
    build_texture_parameters(node, texture_paths_info, version_folder, version)

def get_texture_paths(project=None,
                      version=None,
                      asset=None,
                      asset_type=None,
                      first_name=None,
                      last_name=None,
                      published=None,
                      variant=None):
    """
    Finds all textures, given the current context, 
    getting a list of all their filtered name and filepath 
    in addition to folder or the provided version
    """
    
    from houdini_pipeline import shotgun
    from pathlib import Path
    import re
    
    tk = shotgun.get_tk()
            
    if version == "latest":
        template_path = tk.templates['houdini_wip_asset_textures_version']
    
        fields = {
            "Asset": asset,
            "Step": "surfacing",
            "Task": "surfacing",
            "asset_type": asset_type,
            "HumanUser.firstname": first_name,
            "HumanUser.lastname": last_name
        }
        
        versions = tk.paths_from_template(template_path, fields)
        versions.sort()
        version_folder = versions[-1]
    else:
        template = tk.templates["houdini_wip_asset_textures_version"]
    
        fields = {
            "Asset": asset,
            "Step": "surfacing",
            "Task": "surfacing",
            "asset_type": asset_type,
            "version": int(version),
            "HumanUser.firstname": first_name,
            "HumanUser.lastname": last_name,
        }
        
        version_folder = template.apply_fields(fields)
    
    version_folder = Path(version_folder)

    target_extensions = [".exr", ".jpeg", ".jpg", ".png"]
    
    texture_paths = set()
    
    for file in version_folder.rglob("*"):
        if file.is_file() and file.suffix.lower() in target_extensions:
            texture_paths.add(get_udim_file(file))
    
    texture_paths_info = []
    for texture_path in texture_paths:
        # name = str(texture_path.relative_to(version_folder))
        name = str(texture_path.name)
        filtered_name = re.sub(r'[/\\ ><()]', '_', name)
        texture_paths_info.append((filtered_name, str(texture_path)))
    
    texture_paths_info = sorted(texture_paths_info, key=lambda x: x[1])
        
    return texture_paths_info, version_folder, version

def get_udim_file(filepath):
    """If a given filepath contains a UDIM, return a special UDIM filepath"""
    import re
    
    filename = filepath.name
    parent_folder = filepath.parent
    
    udim_pattern = re.compile(r'(?<!\d)(\d{4,})(?!\d)')
    
    match = udim_pattern.search(filename)
    
    if match:
        udim_name = udim_pattern.sub("<UDIM>", filename)
        udim_path = parent_folder / udim_name
        return udim_path
        
    return filepath
    
def build_texture_parameters(node, texture_paths_info, version_folder, version):
    """Dynamically updates the node's parameter UI with labels, menus and buttons for each texture"""
    if  len(node.inputs()) != 1 or node.inputs()[0].type().name() != "materiallibrary":
        hou.ui.displayMessage("Connect the input of the texture importer to a single material library node.", title="Input Error")
        return
    
    ptg = node.parmTemplateGroup()
    folder_name = "textures_list"
    
    version_str = str(version)

    existing_folder = ptg.find(folder_name)
    if existing_folder:
        ptg.remove(folder_name)

    folder = hou.FolderParmTemplate(folder_name, "Textures List")
    
    material_nodes = get_input_material_nodes(node)
    materials = [m.name() for m in material_nodes]
    
    update_all_dropdown_parm = hou.MenuParmTemplate(
            name=f"update_all_dropdown",
            label="Material",
            menu_items=materials,
            menu_labels=materials,
            # default_value=0
    )
    # update_all_dropdown_parm.setJoinWithNext(True)
    
    place_all_textures_to_current_version_parm_callback_script = (
        f"import hou; "
        f"node = kwargs['node']; "
        f"material = node.parm(f'update_all_dropdown').evalAsString(); "
        f"hou.phm().place_all_textures({texture_paths_info}, material, node);"
        f"hou.ui.displayMessage("
        f"f'Created / Updated all primary textures for the material, {{material}}, to version: {version_str}', "
        f"title='Created / Updated Primary Textures'"
        f")"
    )
    place_all_textures_to_material_parm = hou.ButtonParmTemplate(
        name=f"place_all_textures_to_material_btn",
        label="Create / Update All Primary Textures in the Selected Material",
        script_callback=place_all_textures_to_current_version_parm_callback_script,
        script_callback_language=hou.scriptLanguage.Python
    )
    
    update_all_textures_to_current_version_parm_callback_script = (
        f"import hou; "
        f"node = kwargs['node']; "
        f"material = node.parm(f'update_all_dropdown').evalAsString(); "
        f"hou.phm().update_all_textures({texture_paths_info}, material, node);"
        f"hou.ui.displayMessage("
        f"f'Updated ALL textures for the material, {{material}}, to version: {version_str}.', "
        f"title='Update All Textures'"
        f")"
    )
    update_all_textures_to_current_version_parm = hou.ButtonParmTemplate(
        name=f"update_all_textures_to_current_version_btn",
        label="Update All Listed Textures to Current Version",
        script_callback=update_all_textures_to_current_version_parm_callback_script,
        script_callback_language=hou.scriptLanguage.Python
    )
    
    sep1_parm = hou.SeparatorParmTemplate("separator1")
    
    folder.addParmTemplate(update_all_dropdown_parm)
    folder.addParmTemplate(place_all_textures_to_material_parm)
    folder.addParmTemplate(update_all_textures_to_current_version_parm)
    folder.addParmTemplate(sep1_parm)
        
    for i, texture_path_info in enumerate(texture_paths_info):
        tex_id = f"tex_{i}"

        path_parm = hou.StringParmTemplate(
            name=f"{tex_id}_path",
            label=f"Texture {i+1}",
            num_components=1,
            default_value=(texture_path_info[0],)
        )
        # path_parm.setJoinWithNext(True)

        dropdown_parm = hou.MenuParmTemplate(
            name=f"{tex_id}_type",
            label="Material",
            menu_items=materials,
            menu_labels=materials,
            # default_value=0
        )
        # dropdown_parm.setJoinWithNext(True)
        
        main_btn_callback_script = (
            f"import hou; "
            f"node = kwargs['node']; "
            f"material = node.parm(f'{tex_id}_type').evalAsString(); "
            f"hou.phm().create_texture({texture_path_info}, material, node, False);"
            f"hou.ui.displayMessage("
            f"f'Created / Updated primary node, {texture_path_info[0]}, for the material, {{material}}, to version: {version_str}.', "
            f"title='Created / Updated Primary Node'"
            f")"
        )
        primary_btn_parm = hou.ButtonParmTemplate(
            name=f"{tex_id}_main_btn",
            label="Create / Update Primary Node",
            script_callback=main_btn_callback_script,
            script_callback_language=hou.scriptLanguage.Python
        )
        primary_btn_parm.setJoinWithNext(True)
        
        create_additional_btn_callback_script = (
            f"import hou; "
            f"node = kwargs['node']; "
            f"material = node.parm(f'{tex_id}_type').evalAsString(); "
            f"hou.phm().create_texture({texture_path_info}, material, node, True);"
            f"hou.ui.displayMessage("
            f"f'Created additional node of texture, {texture_path_info[0]}, for the material, {{material}}, to version: {version_str}.', "
            f"title='Created / Additional Node'"
            f")"
        )
        create_additional_btn_parm = hou.ButtonParmTemplate(
            name=f"{tex_id}_create_additional_btn",
            label="Create Additional Nodes",
            script_callback=create_additional_btn_callback_script,
            script_callback_language=hou.scriptLanguage.Python
        )

        sep_parm = hou.SeparatorParmTemplate(f"{tex_id}_separator")
        
        folder.addParmTemplate(path_parm)
        folder.addParmTemplate(dropdown_parm)
        folder.addParmTemplate(primary_btn_parm)
        folder.addParmTemplate(create_additional_btn_parm)
        folder.addParmTemplate(sep_parm)
        
    # sep2_parm = hou.SeparatorParmTemplate("separator2")

    open_folder_callback_script = (
        f"import os; "
        f"os.system('xdg-open \"{version_folder}\"')"
    )
    open_folder_parm = hou.ButtonParmTemplate(
        name=f"open_folder_btn",
        label="Open Folder of Current Version",
        script_callback=open_folder_callback_script,
        script_callback_language=hou.scriptLanguage.Python
    )
    
    # folder.addParmTemplate(sep2_parm)
    folder.addParmTemplate(open_folder_parm)
    
    ptg.append(folder)
    node.setParmTemplateGroup(ptg)

def get_input_material_nodes(node):
    """Given the current node, it grabs the material nodes of the input node"""
    input = node.inputs()[0]
    
    material_nodes = [c for c in input.children() if c.type().name() == "subnet"]
    
    return material_nodes
    
def create_texture(texture_path_info, material, node, additional):
    """Creates the texture as an mltx image"""
    material_node = node.inputs()[0].node(material)
    
    if additional or not material_node.node(texture_path_info[0]):
        mtlx_image_node = material_node.createNode("mtlximage", texture_path_info[0])
    else:
        mtlx_image_node = material_node.node(texture_path_info[0])
    mtlx_image_node.parm("file").set(str(texture_path_info[1]))
    
def place_all_textures(texture_paths_info, material, node):
    """Places all textures of the current version"""
    material_node = node.inputs()[0].node(material)
    children_nodes = material_node.children()

    for texture_path_info in texture_paths_info:
        create_texture(texture_path_info, material, node, False)
    
def update_all_textures(texture_paths_info, material, node):
    """Updates all textures to the current version"""
    material_node = node.inputs()[0].node(material)
    children_nodes = material_node.children()

    for texture_path_info in texture_paths_info:
        for children_node in children_nodes:
            if children_node.name().startswith(texture_path_info[0]):
                children_node.parm("file").set(str(texture_path_info[1]))
                