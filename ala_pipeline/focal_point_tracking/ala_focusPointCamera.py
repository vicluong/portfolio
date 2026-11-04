import maya.cmds as cmds
from functools import partial

def create_focus_point_camera_link() -> None:
    selection = cmds.ls(sl=True)

    if len(selection) != 1:
        cmds.error("Select one camera.")

    # Check if selected is a shape, if so, get its transform
    camera = selection[0]
    if cmds.nodeType(camera) == 'camera':
        camera = cmds.listRelatives(camera, parent=True)[0]
    
    # Verify it's a camera by checking its shape
    shapes = cmds.listRelatives(camera, shapes=True)

    if not shapes or len(shapes) != 1:
        cmds.error("The selected object needs one camera node.")

    if cmds.nodeType(shapes[0]) == 'camera':
        print(f"Selected Camera: {camera}")
    else:
        cmds.error("Selection is not a camera.")

    if cmds.attributeQuery("focusPointAttached", node=camera, exists=True):
        cmds.error("Camera already has a focus point attached to it.")

    if cmds.getAttr(f"{camera}.depthOfField") == False:
        cmds.error("Enable depth of field to create the focus point locator")

    # Get previous state of focusDistance lock and inputs to place back in after the focus point is deleted
    prev_lock = cmds.getAttr(f"{camera}.focusDistance", lock=True)
    if prev_lock:
        cmds.setAttr(f"{camera}.focusDistance", lock=False)

    prev_inputs = cmds.listConnections(f"{camera}.focusDistance", destination=False, source=True, plugs=True)
    if prev_inputs:
        for input in prev_inputs:
            cmds.disconnectAttr(input, f"{camera}.focusDistance")

    camera_world_matrix, focus_point, focus_point_matrix, dist_node = attach_focus_point(camera)
    start_point, measure_node = create_distance_measure(camera, camera_world_matrix)

    cmds.select(focus_point, r=True)

    cmds.scriptJob(attributeChange=[f"{focus_point}.visibility", 
                                    partial(toggle_camera_connection, camera, dist_node, measure_node)])
    
    cmds.scriptJob(attributeDeleted=[f"{focus_point}.matrix", 
                                     partial(cleanup_nodes, camera, camera_world_matrix, focus_point_matrix, 
                                             dist_node, start_point, measure_node, prev_lock, prev_inputs)])

def attach_focus_point(camera: str) -> tuple[str, str, str]:
    """Creates a focus point locator that can dynamically change the camera's focus distance based on the 
     distance between it and the camera"""
    # Create a decomposeMatrix to get the world translation of the selected camera
    camera_world_matrix = cmds.createNode("decomposeMatrix", n="focusPointUtilityMatrix")
    cmds.connectAttr(f"{camera}.worldMatrix", f"{camera_world_matrix}.inputMatrix")
    camera_pos = cmds.getAttr(f"{camera_world_matrix}.outputTranslate")[0]

    focus_point = cmds.spaceLocator(n=f"{camera}_focus_point", a=True, r=False)[0]
    cmds.setAttr(f"{focus_point}.translate", camera_pos[0], camera_pos[1], camera_pos[2] - 2)
    # Create a decomposeMatrix to get the world translation of the focus point
    focus_point_matrix = cmds.createNode("decomposeMatrix", n="focusPointLocatorMatrix")
    cmds.connectAttr(f"{focus_point}.worldMatrix", f"{focus_point_matrix}.inputMatrix")

    # Using the two world translations from the camera and focus point, get the distance and connect it to the focusDistance attribute
    dist_node = cmds.createNode("distanceBetween", n=f"{camera}ToFocusDist")
    cmds.connectAttr(f"{camera_world_matrix}.outputTranslate", f"{dist_node}.point1")
    cmds.connectAttr(f"{focus_point_matrix}.outputTranslate", f"{dist_node}.point2")
    cmds.connectAttr(f"{dist_node}.distance", f"{camera}.focusDistance", force=True)

    camera_parent = cmds.listRelatives(camera, parent=True)
    if camera_parent:
        cmds.parent(focus_point, camera_parent)

    cmds.addAttr(camera, longName="focusPointAttached", hidden=True)

    return (camera_world_matrix, focus_point, focus_point_matrix, dist_node)

def create_distance_measure(camera: str, camera_world_matrix: str) -> tuple[str, str]:
    """Create a visible distance measure from the camera to the focus point"""
    camera_pos = cmds.getAttr(f"{camera_world_matrix}.outputTranslate")[0]

    start_point = cmds.spaceLocator(n=f"{camera}_start_point", a=True, r=False)[0]
    cmds.setAttr(f"{start_point}.translate", camera_pos[0], camera_pos[1], camera_pos[2])

    measure_shape = cmds.distanceDimension(sp=(camera_pos[0], camera_pos[1], camera_pos[2]), ep=(camera_pos[0], camera_pos[1], camera_pos[2] - 2))
    measure_node = cmds.listRelatives(measure_shape, parent=True)[0]
    measure_node = cmds.rename(measure_node, f"{camera}_measure")

    cmds.parent(start_point, camera)
    cmds.setAttr(f"{start_point}.translate", lock=True)
    cmds.setAttr(f"{start_point}.visibility", False)
    cmds.parent(measure_node, camera)
    cmds.setAttr(f"{measure_node}.translate", lock=True)

    return (start_point, measure_node)

def toggle_camera_connection(camera: str, dist_node: str, measure_node: str) -> None:
    """Toggle the distance input to the camera's focus distance when the focus point's visibility is toggled"""
    inputs = cmds.listConnections(f"{camera}.focusDistance", destination=False, source=True)
    if inputs:
        cmds.disconnectAttr(f"{dist_node}.distance", f"{camera}.focusDistance")
        cmds.setAttr(f"{measure_node}.visibility", False)
    else:
        cmds.connectAttr(f"{dist_node}.distance", f"{camera}.focusDistance")
        cmds.setAttr(f"{measure_node}.visibility", True)

def cleanup_nodes(camera: str, camera_world_matrix: str, focus_point_matrix: str, dist_node: str, start_point: str, 
                  measure_node: str, prev_lock: bool, prev_inputs: list[str]) -> None:
    """Removes all nodes created for the focus point tool and restores old connections and lock for the camera's focusDistance"""
    if cmds.objExists(camera_world_matrix):
        cmds.delete(camera_world_matrix)
    if cmds.objExists(focus_point_matrix):
        cmds.delete(focus_point_matrix)
    if cmds.objExists(dist_node):
        cmds.delete(dist_node)
    if cmds.objExists(start_point):
        cmds.delete(start_point)
    if cmds.objExists(measure_node):
        cmds.delete(measure_node)

    cmds.deleteAttr(camera, at="focusPointAttached")

    cmds.setAttr(f"{camera}.focusDistance", lock=False)

    if prev_inputs:
        for input in prev_inputs:
            cmds.connectAttr(input, f"{camera}.focusDistance", force=True)

    if prev_lock:
        cmds.setAttr(f"{camera}.focusDistance", lock=prev_lock)

