import mari
import mariUsd
import sgtk
import tractor.api.author
import os
import re
from pathlib import Path
import PySide2.QtWidgets as widgets
from mari_pipeline import utils

def GetMaterialExportRoot(texture_output_template_name, geo, shader_name=None):

    try:
        try:
            asset_name_and_version = mari.projects.current().name()
        except:
            mari.utils.message('Please open a project first.')
            return
        engine = sgtk.platform.current_engine()

        tk = engine.sgtk
        material_output_template = tk.templates[texture_output_template_name]
        fields = engine.context.as_template_fields(material_output_template)

        try:
            fields["name"] = geo.metadata('geo_default_name')
        except:
            fields["name"] = geo.name()

        if shader_name:
            fields['material_name'] = shader_name

        fields["version"] = int(asset_name_and_version.split("_")[-1][1:])


        output_path = material_output_template.apply_fields(fields)
    except Exception as e:
        print("Failed to build the Mari output path: %s" % e)
        return None
    
    return output_path

def GetChannelExportPath(channel):
    try:
        try:
            asset_name_and_version = mari.projects.current().name()
        except:
            mari.utils.message('Please open a project first.')
            return
        engine = sgtk.platform.current_engine()

        tk = engine.sgtk

        texture_output_template = tk.templates['mari_wip_texture_export_path']

        fields = engine.context.as_template_fields(texture_output_template)

        fields["name"] = mari.geo.current().name()
        fields["channel"] = channel.name()
        fields["version"] = int(asset_name_and_version.split("_")[-1][1:])
        fields["UDIM"] = "$UDIM"

        colourspace = channel.colorspaceConfig().resolveColorspace(mari.ColorspaceConfig.ColorspaceStage.COLORSPACE_STAGE_OUTPUT)

        if("acescg" in colourspace.lower()):
            fields["colorspace"] = "acescg"
        elif("raw" in colourspace.lower()):
            fields["colorspace"] = "linear"
        else:
            mari.utils.message("Channel '%s' is in the incorrect colourspace. Ensure it is in AcesCG or Raw" % channel.name())

        output_path = texture_output_template.apply_fields(fields)
    except Exception as e:
        print("Failed to build the Mari output path: %s" % e)
        return None
    
    return output_path

def MakeTexsJob(asset_name_and_version, directory):
    job = tractor.api.author.Job()\

    cmd = ["maketexs", "--dir=%s" % directory, "--mode=periodic", "--skipaces"]
    rez_resolve = os.getenv('REZ_USED_RESOLVE')
    rez_packages = 'rez-pkgs=' + rez_resolve
    job.title = '{0}'.format("maketexs_"+asset_name_and_version)
    job.envkey = [rez_packages]
    job.atleast = 1
    job.service = 'bash'
    job.tier = 'default'
    job.atmost = job.atleast

    job.newTask(title=job.title, argv=cmd)

    jobid = job.spool()

    return jobid

def ExportChannels():
    allowed_channel_names = ["basecolor", "height", "SSS", "roughness", "normal", "metallic", "opacity"]

    try:
        asset_name_and_version = mari.projects.current().name()
    except:
        mari.utils.message('Please open a project first.')
        return

    geo = mari.geo.current()

    for c in geo.channelList():
        if(c.name() not in allowed_channel_names):
            mari.utils.message("Channel '%s' is not an allowed channel. Please rename it to one of the following: %s" % (c.name(), ", ".join(allowed_channel_names)))
            return
        layer = None
        
        output_path = GetChannelExportPath(c)

        if not output_path:
            mari.utils.message("Please make sure your file is saved in ShotGrid.")
            return

        output_path_folder = "/".join(output_path.split("/")[:-1])

        if layer:
            # publish a specific layer:
            layer.exportImages(output_path)
        else:
            # publish the entire channel, flattened
            layers = c.layerList()
            if len(layers) == 1:
                # only one layer so just publish it:
                # Note - this works around an issue that was reported (#27945) where flattening a channel
                # with only a single layer would cause Mari to crash - this bug was not reproducible by
                # us but happened 100% for the client!
                try:
                    layer = layers[0]
                    layer.exportImages(output_path)
                except Exception as e:
                    mari.utils.message("Error exporting channel '%s': %s" % (c.name(), str(e)))
                    return
            elif len(layers) > 1:
                # flatten layers in the channel and publish the flattened layer:
                # remember the current channel:
                # duplicate the channel so we don't operate on the original:
                duplicate_channel = geo.createDuplicateChannel(c)
                try:
                    # flatten it into a single layer:
                    flattened_layer = duplicate_channel.flatten()
                    # export the images for it:
                    flattened_layer.exportImages(output_path)
                except Exception as e:
                    mari.utils.message("Error exporting channel '%s': %s" % (c.name(), str(e)))
                    return
                finally:
                    # set the current channel back - not doing this will result in Mari crashing
                    # when the duplicated channel is removed!
                    geo.setCurrentChannel(c)
                    # remove the duplicate channel, destroying the channel and the flattened layer:
                    geo.removeChannel(duplicate_channel, geo.DESTROY_ALL)
            else:
                mari.utils.message("Channel '%s' doesn't appear to have any layers!" % c.name())
                return 
                    
    #cleanTexsProcess = subprocess.Popen("maketexs --dir=%s --clean" % output_path_folder, stdout=subprocess.PIPE, shell=True)
    #makeTexsProcess = subprocess.call(["maketexs", "--dir=%s" % output_path_folder, "--mode=periodic", "--skipaces"])
    jobid = MakeTexsJob(asset_name_and_version, output_path_folder)
    
    #print(makeTexsProcess.communicate())
    
    mari.utils.message("Successfully exported textures for '%s' and job to make tex files sent off with id %s!" % (asset_name_and_version, str(jobid)))

def ExportAllGeoPxrSurfaces(texture_output_dir=None, lookfile_output_dir=None, texture_output_template_name=None, lookfile_output_template_name=None, texture_output_material_template_name=None, lookfile_output_material_template_name=None, pxrsurface=None ,exportManager=None, display=False):
    
    for geo in utils.get_all_sg_geo():
        ExportPxrSurface(texture_output_dir=texture_output_dir, lookfile_output_dir=lookfile_output_dir, texture_output_template_name=texture_output_template_name, lookfile_output_template_name=lookfile_output_template_name, texture_output_material_template_name=texture_output_material_template_name, lookfile_output_material_template_name=lookfile_output_material_template_name, pxrsurface=pxrsurface, exportManager=exportManager, display=display, geo=geo)

def ExportPxrSurface(texture_output_dir=None, lookfile_output_dir=None, texture_output_template_name=None, lookfile_output_template_name=None, texture_output_material_template_name=None, lookfile_output_material_template_name=None, pxrsurface=None ,exportManager=None, display=False, geo=None):

    if not geo:
        geo = mari.geo.current()
    
    try:
        asset_name_and_version = mari.projects.current().name()
    except:
        mari.utils.message('Please open a project first.')
        return
    
    geo_metadata = geo.metadata('Variants')
    geo_model_variant = None
    if geo_metadata != None:
        geo_model_variant = re.search(r"model_variant=(\w+)}", geo_metadata)
        if geo_model_variant != None:
            geo_model_variant = geo_model_variant.group(1)

    if not exportManager:
        exportManager = mariUsd.usdMultiShaderExportDialog.generateUsdMultiShaderExportWidget()
        #Clear materials
        exportManager.model.removeMaterials([*range(len(exportManager.model.material_list))])

        #Setup new export item for PxrSurface
        exportManager.model.addMaterial()

        #Set export material name to Mari Scene name
        exportManager.model.material_list[0].name = asset_name_and_version
    if not pxrsurface:
        #Get export PxrSurface from model shaders
        if 'PxrSurface' not in exportManager.model.shader_map.keys():
            msg = "No PxrSurface Shader Networks found"
            if display:
                mari.utils.message(msg)
            else:
                raise Exception(msg)
            return
        pxrsurfaces = []
        
        for shader in geo.shaderList():
            if not shader.shaderModel():
                continue
            elif shader.shaderModel().id() == "PxrSurface":
                pxrsurfaces.append(shader)

        if len(pxrsurfaces) == 0:
            msg = "No PxrSurface Shader Networks found"
            if display:
                mari.utils.message(msg)
            else:
                raise Exception(msg)
            return
    else:
        pxrsurfaces = [pxrsurface]
    for pxrsurface in pxrsurfaces:
        
        # Get output directory and create dirs if don't exist
        # Uses material template if geo has model_variant metadata so we don't break existing WIP exports.
        if not texture_output_dir:
            if geo_model_variant:
                texture_output_dir_variant = GetMaterialExportRoot(texture_output_material_template_name, geo, pxrsurface.name())
            else:
                texture_output_dir_variant = GetMaterialExportRoot(texture_output_template_name, geo)
        else:
            texture_output_dir_variant = texture_output_dir

        if not lookfile_output_dir:
            if geo_model_variant:
                lookfile_output_dir_variant = GetMaterialExportRoot(lookfile_output_material_template_name, geo, pxrsurface.name())
            else:
                lookfile_output_dir_variant = GetMaterialExportRoot(lookfile_output_template_name, geo)
        else:
            lookfile_output_dir_variant = lookfile_output_dir

        if not texture_output_dir_variant or not lookfile_output_dir_variant:
            mari.utils.message("Please make sure your file is saved in ShotGrid.")
            return
    
        #If no bake point or channel node, then nothing to output
        if len(mariUsd.usdExportManagerTab.ExportItem_Model.advancedInputList(pxrsurface))==0:
            msg = "No MultiChannel Bake Point or Channel node attached to Shader \"{0}\"".format(pxrsurface.name())
            if display:
                mari.utils.message(msg)
            else:
                raise Exception(msg)
            return
        
        exportManager.model.material_list[0].shader_assignments["PxrSurface"] = pxrsurface
        exportManager.model.saveMaterials()

        if not os.path.exists(texture_output_dir_variant):
            os.makedirs(texture_output_dir_variant, exist_ok=True)
        
        if not os.path.exists(lookfile_output_dir_variant):
            os.makedirs(lookfile_output_dir_variant, exist_ok=True)

        exportManager.export_usd_target_dir_widget.new_path_added(texture_output_dir_variant)
        exportManager.look_file_widget.new_path_added(lookfile_output_dir_variant+"/LookFile.usda")
        exportManager.assembly_file_widget.new_path_added(lookfile_output_dir_variant+"/Assembly.usda")
        exportManager.root_name_widget.setText("/"+"_".join(asset_name_and_version.split("_")[:-1]))

        if(mari.current.project().info().modelPath().endswith('.usd') or mari.current.project().info().modelPath().endswith('.usda')):
            exportManager.payload_file_widget.new_path_added(mari.current.project().info().modelPath())
        else:
            engine = sgtk.platform.current_engine()
            shotgun = engine.tank.shotgun
            try:
                usd_pub = shotgun.find_one("PublishedFile", [['entity.Asset.code', "is", "_".join(asset_name_and_version.split("_")[:-1])], ['published_file_type.PublishedFileType.code', "is", 'USD File'], ['version_number', 'is', int(mari.current.geo().currentVersionName()[1:])]], fields = ["id", "version_number", "path"], order = [{'field_name':'version_number', 'direction':'desc'}])
            except Exception as e:
                msg = "Error finding USD version of model: " + str(e)
                if display:
                    mari.utils.message(msg)
                else:
                    raise Exception(msg)
                return
            else:
                exportManager.payload_file_widget.new_path_added(usd_pub["path"]["local_path"])

        exportManager.saveSettings()
        try:
            exportUsd(exportManager)
        except mariUsd.usdShadeExport.UsdShadeExportError as e:
            print("Error prevented shader export: " + str(e))
        else:
            try:
                jobid = MakeTexsJob(asset_name_and_version, texture_output_dir_variant)
            except Exception as e:
                msg = "Error creating maketexs farm job: " + str(e)
                if display:
                    mari.utils.message(msg)
                else:
                    raise Exception(msg)
            else:
                if display:
                    msgBox = widgets.QMessageBox()
                    msgBox.setText("Successfully exported shader " + asset_name_and_version)
                    msgBox.setWindowTitle("Message")
                    msgBox.setIcon(widgets.QMessageBox.Information)
                    msgBox.setStandardButtons(widgets.QMessageBox.Ok | widgets.QMessageBox.Open)
                    msgBox.setDefaultButton(widgets.QMessageBox.Ok)
                    msgBox.setInformativeText("Making texs on farm with jobid " + str(jobid))
                    returnValue = msgBox.exec()

                    if returnValue == widgets.QMessageBox.Open:
                        os.system('xdg-open "%s"' % texture_output_dir_variant)
            #mari.utils.message(, buttons=widgets.QMessageBox.StandardButtons(widgets.QMessageBox.StandardButton.Ok|widgets.QMessageBox.StandardButton.Open))

#Adapted from mariUsd.usdMultiShaderExportDialog - added error raise for GUI reasons
def exportUsd(exportManager):
        exportManager.saveSettings()
        exportManager.model.saveMaterials()

        try:
            usd_export_parameters = mariUsd.usdShadeExport.UsdExportParameters()
            usd_export_parameters.setExportRootPath(exportManager.export_usd_target_dir_widget.path())
            usd_export_parameters.setLookfileTargetFilename(exportManager.look_file_widget.path())
            usd_export_parameters.setAssemblyTargetFilename(exportManager.assembly_file_widget.path())
            usd_export_parameters.setPayloadSourcePath(exportManager.payload_file_widget.path())
            usd_export_parameters.setStageRootPath(exportManager.root_name_widget.text())
            usd_export_parameters.setExportOverrides({"RESOLUTION":exportManager.default_size_combo_box.currentText(), "DEPTH":exportManager.default_depth_combo_box.currentText()})

            usd_material_sources = []
            for material in exportManager.model.material_list:
                if not material.checked:
                    continue

                for shader_model_name in material.shader_assignments:
                    shader = material.shader_assignments[shader_model_name]
                    if not shader:
                        continue

                    node = shader.shaderNode()
                    if not node:
                        continue

                    node_graph = node.parentNodeGraph()
                    if not node_graph:
                        continue

                    geo_entity = node_graph.parentGeoEntity()
                    if not geo_entity:
                        continue

                    current_geo_version = geo_entity.currentVersion()
                    if not current_geo_version:
                        continue

                    # Execute the ExportExportItem callback function for the vendor.
                    export_export_item_callback = mariUsd.usdShadeExport.functionCallbackForShader(shader_model_name, mariUsd.usdShadeExport.CALLBACK_NAME_EXPORT_EXPORT_ITEM)

                    usd_material_source = mariUsd.usdShadeExport.UsdMaterialSource(material.name)
                    usd_material_source.setBindingLocations(current_geo_version.sourceMeshLocationList())
                    usd_material_source.setSelectionGroups(material.selection_groups)
                    usd_shader_source = mariUsd.usdShadeExport.UsdShaderSource(shader)
                    usd_shader_source.setUvSetName(exportManager.uv_set_name_widget.text())

                    for export_item, shader_input_name in mariUsd.usdMultiShaderExportDialog.getExportItems(material, shader):
                        usd_shader_source.setInputExportItem(shader_input_name, export_item)
                        if export_export_item_callback is not None:
                            export_export_item_callback(export_item)
                    usd_material_source.setShaderSource(shader.shaderModel().id(), usd_shader_source)
                    usd_material_sources.append(usd_material_source)

            mariUsd.usdShadeExport.exportUsdShadeLook(usd_export_parameters, usd_material_sources)
        except mariUsd.usdShadeExport.UsdShadeExportError as error:
            mari.app.log("USD Multi Shader Export Error : %s" % error.message)
            mari.utils.message(error.message, error.title, icon=widgets.QMessageBox.Critical, details=error.details)
            raise error

def GetChannelExportPathHoudini():
    try:
        try:
            asset_name_and_version = mari.projects.current().name()
        except:
            mari.utils.message('Please open a project first.')
            return
        engine = sgtk.platform.current_engine()

        tk = engine.sgtk
        texture_output_template = tk.templates['houdini_wip_asset_textures_version']

        fields = engine.context.as_template_fields(texture_output_template)
        fields["version"] = int(asset_name_and_version.rsplit("_v", 1)[1])

        output_path = texture_output_template.apply_fields(fields)

        object_name = asset_name_and_version.rsplit("_v", 1)[0]

        output_path = str(Path(output_path) / object_name)

    except Exception as e:
        print("Failed to build the Mari output path: %s" % e)
        return None
    
    return output_path

def ExportChannelsManagerHoudini():
    current_geo = mari.geo.current()
    if not current_geo:
        mari.utils.message("No active geometry found in the scene.")
        return
        
    export_items = mari.exports.exportItemList(current_geo)
    
    for item in export_items:
        mari.exports.removeExportItem(item)

    for channel in current_geo.channelList():
        eItem = mari.ExportItem()
        eItem.setSourceNode(channel.channelNode())
        eItem.setFileTemplate("$CHANNEL.$UDIM.tif")
        mari.exports.addExportItem(eItem, current_geo)

    export_items = mari.exports.exportItemList(current_geo)

    for item in export_items:
        item.setDepth("16bit (Half)")
        item.setResolution("4096 x 4096")
        item.setColorspace("ACEScg")

        object_name = mari.projects.current().name().rsplit("_v", 1)[0]
        file_template = f"{object_name}.$CHANNEL.$UDIM.exr"
        item.setFileTemplate(file_template)

    mari.app.activateMainWindow()
    main_window = widgets.QApplication.activeWindow()
    dialog = mari.system.batch_export_dialog.ExportDialog(parent=main_window)
    dialog.show()

    tab_widget = dialog.findChild(widgets.QTabWidget)
    first_tab = tab_widget.widget(0)

    for label in first_tab.findChildren(widgets.QLabel):
        if "Export Root Path" in label.text():
            # Find the QLineEdit closest to the label's Y-position
            line_edits = first_tab.findChildren(widgets.QLineEdit)
            target_edit = min(line_edits, 
                              key=lambda edit: abs(edit.y() - label.y()))
            channel_export_path = GetChannelExportPathHoudini()
            target_edit.setText(channel_export_path)