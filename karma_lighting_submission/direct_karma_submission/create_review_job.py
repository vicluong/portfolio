from optparse import OptionParser

from houdini_pipeline import lighting_diagnostic_job as ldj
from houdini_pipeline import auto_comp_job as acj


def main():
    p = OptionParser()
    p.add_option("-s", "--submissionshot", dest='submission_shot', action='store')
    p.add_option("-d", "--diagnostic", dest='diagnostic', action='store')
    p.add_option("-B", "--bashcomp", dest='bashcomp', action='store')
    p.add_option("-f", "--framerange", dest='framerange', action='store')

    opts, args = p.parse_args()

    print(opts)

    if bool(opts.diagnostic) == bool(opts.bashcomp):
        print("Error: Specify exactly one of --diagnostic or --bashcomp.")
        return   

    submission_shot = opts.submission_shot
    framerange = opts.framerange

    if opts.diagnostic:
        ldj.create_lighting_diagnostic_job(submission_shot, framerange)
    elif opts.bashcomp:
        acj.create_auto_comp_job(submission_shot, framerange)


if __name__ == "__main__":
    main()
