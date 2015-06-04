import argparse
import json
import os
import subprocess
import tempfile

import configuration
import library


rsa_keyfile_path = '/etc/irods/server.key'
ssl_certificate_path = '/etc/irods/server.crt'
diffie_hellman_parameters_path = '/etc/irods/dhparams.pem'

def enable_ssl(deployed_zone_bundle):
    zone = deployed_zone_bundle['zones'][0]
    install_ssl_files_zone(zone)
    update_irods_environment_zone(zone)
    update_core_re_zone(zone)

def install_ssl_files_zone(zone):
    with tempfile.NamedTemporaryFile(prefix='rsa-keyfile') as f_rsa_keyfile:
        create_rsa_keyfile(f_rsa_keyfile.name)
        with tempfile.NamedTemporaryFile(prefix='self-signed-certificate') as f_self_signed_certificate:
            create_self_signed_certificate(f_rsa_keyfile.name, f_self_signed_certificate.name)
            with tempfile.NamedTemporaryFile(prefix='diffie-hellman-parameters') as f_diffie_hellman_parameters:
                create_diffie_hellman_parameters(f_diffie_hellman_parameters.name)

                files_to_copy = [(f_rsa_keyfile.name, rsa_keyfile_path, '0600'),
                                 (f_self_signed_certificate.name, ssl_certificate_path, '0666'),
                                 (f_diffie_hellman_parameters.name, diffie_hellman_parameters_path, '0600')]
                for src, dst, perms in files_to_copy:
                    library.copy_file_to_zone(zone, src, dst, 'irods', 'irods', perms)

def create_rsa_keyfile(filename):
    subprocess.check_call(['openssl', 'genrsa', '-out', filename])

def create_self_signed_certificate(filename_key, filename_certificate):
    p = subprocess.Popen(['openssl', 'req', '-new', '-x509', '-key', filename_key, '-out', filename_certificate, '-days', '365'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate('\n'*7)
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args, 'stdout [{0}], stderr [{1}]'.format(out, err))

def create_diffie_hellman_parameters(filename):
    subprocess.check_call(['openssl', 'dhparam', '-2', '-out', filename, '1024'])

def update_irods_environment_zone(zone):
    servers = library.get_servers_from_zone(zone)
    host_list = [server['deployment_information']['ip_address'] for server in servers]

    complex_args = {
        'filename': '/var/lib/irods/.irods/irods_environment.json',
        'update_dict': {
            'irods_ssl_certificate_key_file': rsa_keyfile_path,
            'irods_ssl_certificate_chain_file': ssl_certificate_path,
            'irods_ssl_dh_params_file': diffie_hellman_parameters_path,
            'irods_client_server_policy': 'CS_NEG_REQUIRE',
            'irods_ssl_verify_server': 'cert',
            'irods_ssl_ca_certificate_file': ssl_certificate_path,
        }
    }

    library.run_ansible(module_name='update_json_file', complex_args=complex_args, host_list=host_list, sudo=True)

def update_core_re_zone(zone):
    servers = library.get_servers_from_zone(zone)
    host_list = [server['deployment_information']['ip_address'] for server in servers]

    complex_args = {
        'dest': '/etc/irods/core.re',
        'regexp': r'^acPreConnect\(\*OUT\) \{ \*OUT="CS_NEG_DONT_CARE"; \}$',
        'replace': 'acPreConnect(*OUT) { *OUT="CS_NEG_REQUIRE"; }',
    }

    library.run_ansible(module_name='replace', complex_args=complex_args, host_list=host_list, sudo=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enable SSL for iRODS topology tests')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    enable_ssl(zone_bundle)
