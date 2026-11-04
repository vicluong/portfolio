import shotgun_utils
import tractor.api.author


def create_lighting_diagnostic_job(shot_name, frames):
    print("Creating lighting diagnostic job")
    proj_code = shotgun_utils.get_project_code()

    envkey = ['rez-pkgs=nuke_pipeline nuke {0}'.format(proj_code)]

    script = f'$NUKE_BIN -t -- $REZ_NUKE_PIPELINE_ROOT/bin/create_lighting_diagnostic.py -f {frames} -s {shot_name}'

    cmd = [
        '/opt/rez/bin/rez/rez-env',
        'nuke_pipeline',
        'nuke',
        proj_code,
        '--',
        'bash',
        '-c',
        script,
    ]

    job_title = str(f'{shot_name}_light_diagnostic_begin')

    job = tractor.api.author.Job()  
    job.title = job_title
    job.envkey = envkey
    job.atleast = 1
    job.service = 'bash'
    job.tier = 'default'
    job.atmost = job.atleast

    render_task = job.newTask(title=job_title, argv=cmd)

    id = job.spool()

if "__main__" == __name__:
    create_lighting_diagnostic_job()