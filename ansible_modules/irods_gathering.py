#!/usr/bin/python

import os
import socket
import subprocess


def makedirs_catch_preexisting(*args, **kwargs):
    try:
        os.makedirs(*args, **kwargs)
    except OSError as e:
        if e[0] != 17: # 17 == File exists
            raise

def gather(output_root_directory):
    change_permissions_if_exists('/var/lib/irods')
    change_permissions_if_exists('/tmp/irods')

    output_directory = os.path.join(output_root_directory, socket.gethostname())
    makedirs_catch_preexisting(output_directory)

    gathered_files = []
    source_and_predicates = [('/var/lib/irods/iRODS/server/log', all_files),
                             ('/tmp/irods', all_files),
                             ('/var/lib/irods/tests/pydevtest/test-reports', all_files),
                             ('/var/lib/irods/scripts/test-reports', all_files),
                             ('/var/lib/irods/iRODS/server/test/bin', log_files),
                             ('/var/lib/irods', or_(version_files, ini_files)),
                             ('/var/lib/irods/iRODS/installLogs', all_files),
                             ('/var/lib/irods/log', all_files),]
    for s, p in source_and_predicates:
        gathered_files += gather_files_in(s, output_directory, p)
    return gathered_files

def or_(f0, f1):
    return lambda x: f0(x) or f1(x)

def all_files(x):
    return True

def log_files(x):
    return x.endswith('.log')

def version_files(x):
    return os.path.basename(x).startswith('VERSION')

def ini_files(x):
    return x.endswith('.ini')

def gather_files_in(source_directory, output_directory, predicate):
    try:
        gathered_files = []
        for basename in os.listdir(source_directory):
            fullpath = os.path.join(source_directory, basename)
            if os.path.isfile(fullpath):
                if predicate(fullpath):
                    shutil.copy2(fullpath, output_directory)
                    gathered_files.append(fullpath)
    except OSError as e:
        if e.errno != 2: # No such file or directory
            raise
    return gathered_files

def change_permissions_if_exists(directory):
    if os.path.exists(directory):
        subprocess.check_call(['sudo', 'chmod', '-R', '777', directory])

def main():
    module = AnsibleModule(
        argument_spec = dict(
            output_root_directory=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    gathered_files = gather(module.params['output_root_directory'])

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    result['gathered_files'] = gathered_files

    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
