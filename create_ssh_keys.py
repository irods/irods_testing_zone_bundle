from __future__ import print_function

import argparse  
import json
import os
import subprocess
import tempfile

import configuration
import library

ssh_keys_path = '/var/lib/irods/.ssh'
private_ssh_key_path = '/var/lib/irods/.ssh/id_rsa'
public_ssh_key_path = '/var/lib/irods/.ssh/id_rsa.pub'
authorized_keys_path = '/var/lib/irods/.ssh/authorized_keys'

def share_ssh_keys(deployed_zone_bundle):
    zone = deployed_zone_bundle['zones'][0]
    share_ssh_files_zone(zone)

def share_ssh_files_zone(zone):
    with tempfile.NamedTemporaryFile(prefix='ssh-keyfile') as f_ssh_keyfile:
        create_ssh_key_files(f_ssh_keyfile.name)
        tmp_public_key = f_ssh_keyfile.name+'.pub'

        files_to_copy = [(f_ssh_keyfile.name, private_ssh_key_path, '0600'),
                         (tmp_public_key, public_ssh_key_path, '0644'),
                         (tmp_public_key, authorized_keys_path, '0644')]
        for src, dst, perms in files_to_copy:
            print('src: '+src)
            library.copy_file_to_zone(zone, src, dst, 'irods', 'irods', perms)

def create_ssh_key_files(filename):
    p = subprocess.Popen(['ssh-keygen', '-N', '', '-f', filename], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate('y\n')
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args, 'stdout [{0}], stderr [{1}]'.format(out, err))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Share SSH keys for iRODS topology tests')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    share_ssh_keys(zone_bundle)
