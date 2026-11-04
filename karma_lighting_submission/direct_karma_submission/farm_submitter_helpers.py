import hou


# ----------------------------- Get valid items -----------------------------

def get_pass_types(shot: str) -> list[str]:
    parent_node = hou.node("/obj/lopnet1")

    if not parent_node:
        return []

    applicability_nodes = [
        child
        for child in parent_node.children()
        if child.name().startswith("applicability_")
    ]

    pass_types = []

    for applicability_node in applicability_nodes:
        valid_pass = get_valid_pass(shot, applicability_node)
        if valid_pass:
            pass_types.append(valid_pass)

    return pass_types

def get_valid_pass(shot: str, applicability_node: hou.node):
    if is_shot_applicable(applicability_node, shot):
        return applicability_node.name().split("_", 1)[1]

    return None

def is_shot_applicable(applicability_node: hou.node, shot: str) -> bool:
    # Checkbox mode: node has the applicable_shots folder
    ptg = applicability_node.parmTemplateGroup()
    if ptg.find("applicable_shots") is not None:
        checkbox = applicability_node.parm(f"{shot}_checkbox")
        return checkbox is not None and bool(checkbox.eval())

    # Typed mode: fall back to the applicability string
    typed = applicability_node.parm("applicability")
    if typed is None:
        return False
    return shot in typed.evalAsString()

def get_valid_shots():
    valid_shots = []

    parm = hou.node("/obj/alacontext1").parm("ctx_menu")
    shots = parm.menuItems()

    # Remove empty string from list
    shots = [x for x in shots if x]

    for shot in shots:
        pass_types = get_pass_types(shot)
        if pass_types:
            valid_shots.append(shot)

    return valid_shots

# ------------------------------ UI helpers ------------------------------

def refresh_submitter_ui(node: hou.node):
    multi = bool(node.parm("multi_shot").eval())

    remove_folder(node, "specific_passes")
    remove_folder(node, "specific_shots")

    if multi:
        create_shot_checkboxes(node)
    else:
        create_pass_checkboxes(node)

def set_hidden_parm(node: hou.node, name: str, hidden: bool):
    ptg = node.parmTemplateGroup()
    template = ptg.find(name)

    # If current hidden value matches proposed hidden value, don't change hidden value
    if template is None or template.isHidden() == hidden:
        return
    
    template.hide(hidden)
    ptg.replace(name, template)
    node.setParmTemplateGroup(ptg)

def remove_folder(node: hou.node, name: str):
    ptg = node.parmTemplateGroup()
    if ptg.find(name) is not None:
        ptg.remove(name)
        node.setParmTemplateGroup(ptg)

# ----------------------------- Checkbox Creation -----------------------------

def create_pass_checkboxes(node: hou.node):
    shot = node.parm("submission_shot").evalAsString().strip()

    ptg = node.parmTemplateGroup()
    if ptg.find("specific_passes") is not None:
        ptg.remove("specific_passes")

    if shot == "":
        node.setParmTemplateGroup(ptg)
        return

    pass_types = get_pass_types(shot)
    folder = hou.FolderParmTemplate("specific_passes", "Specific Passes")

    print("Pass checkboxes:", pass_types)

    if pass_types:
        for pass_type in pass_types:
            folder.addParmTemplate(
                hou.ToggleParmTemplate(
                    f"{pass_type}_checkbox", f"Pass: {pass_type}", default_value=True
                )
            )
    else:
        folder.addParmTemplate(
            hou.LabelParmTemplate("no_passes_label", "No valid passes for this shot.")
        )

    if ptg.find("submission_shot") is not None:
        ptg.insertAfter("submission_shot", folder)
    else:
        ptg.append(folder)

    sep_parm = ptg.find("sep2ndblock")
    if sep_parm is not None:
        sep_parm.hide(False)
        ptg.replace("sep2ndblock", sep_parm)

    node.setParmTemplateGroup(ptg)

def create_shot_checkboxes(node: hou.node):
    ptg = node.parmTemplateGroup()
    if ptg.find("specific_shots") is not None:
        ptg.remove("specific_shots")

    shots = get_valid_shots()
    folder = hou.FolderParmTemplate("specific_shots", "Specific Shots")

    print("Shot checkboxes:", shots)

    if shots:
        for shot in shots:
            folder.addParmTemplate(
                hou.ToggleParmTemplate(
                    f"{shot}_checkbox", f"Shot: {shot}", default_value=True
                )
            )
    else:
        folder.addParmTemplate(
            hou.LabelParmTemplate("no_shots_label", "No valid shots for this file.")
        )

    sep_parm = ptg.find("sep2ndblock")

    if sep_parm is not None:
        ptg.insertAfter("sep2ndblock", folder)
    else:
        ptg.append(folder)

    sep_parm.hide(True)
    ptg.replace("sep2ndblock", sep_parm)

    node.setParmTemplateGroup(ptg)

# ----------------------------- Applicability Node -----------------------------

def refresh_applicability_shot_checkboxes(node: hou.node):
    ptg = node.parmTemplateGroup()
    if ptg.find("applicable_shots") is not None:
        ptg.remove("applicable_shots")

    parm = hou.node("/obj/alacontext1").parm("ctx_menu")
    shot_items = parm.menuItems()

    # Remove empty string from list
    shots = [x for x in shot_items if x]

    folder = hou.FolderParmTemplate("applicable_shots", "Applicable Shots")

    print("Shot checkboxes:", shots)

    if shots:
        for shot in shots:
            folder.addParmTemplate(
                hou.ToggleParmTemplate(
                    f"{shot}_checkbox", f"Shot: {shot}", default_value=False
                )
            )
    else:
        folder.addParmTemplate(
            hou.LabelParmTemplate("no_shots_label", "No valid shots for this file.")
        )

    reload_parm = ptg.find("reload_btn")

    if reload_parm is not None:
        ptg.insertAfter("reload_btn", folder)
    else:
        ptg.append(folder)

    node.setParmTemplateGroup(ptg)
