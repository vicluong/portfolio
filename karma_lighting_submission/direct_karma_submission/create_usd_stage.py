from optparse import OptionParser
import hou


def main():
    # Rendering frames requires a USD file to work on first in order to render within the blade

    p = OptionParser()
    p.add_option("-f", "--file", dest='file', action='store')
    p.add_option("-n", "--node", dest='node', action='store')
    p.add_option("-o", "--output", dest='output', action='store')
    p.add_option("-F", "--frame", dest='frame', action='store')

    opts, args = p.parse_args()

    hou.hipFile.load(
        opts.file,
        suppress_save_prompt=True,
        ignore_load_warnings=True,
    )

    hou.setFrame(int(opts.frame))

    stage = hou.node(opts.node).stage()

    stage.Export(opts.output)


if __name__ == "__main__":
    main()
