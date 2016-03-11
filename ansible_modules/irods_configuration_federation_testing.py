#!/usr/bin/python


def perform_test_setup(username, module):
    create_user(username, module)
    if get_irods_version() >= (4,):
        create_passthrough_resource(module)

def create_user(username, module):
    module.run_command(['su', '-', 'irods', '-c', 'iadmin mkuser {0} rodsuser'.format(username)], check_rc=True)

def create_passthrough_resource(module):
    import os
    import socket
    hostname = socket.gethostname()
    passthrough_resc = 'federation_remote_passthrough'
    leaf_resc = 'federation_remote_unixfilesystem_leaf'
    leaf_resc_vault = os.path.join('/tmp', leaf_resc)
    module.run_command(['su', '-', 'irods', '-c', 'iadmin mkresc {0} passthru'.format(passthrough_resc)], check_rc=True)
    module.run_command(['su', '-', 'irods', '-c', 'iadmin mkresc {0} unixfilesystem {1}:{2}'.format(leaf_resc, hostname, leaf_resc_vault)], check_rc=True)
    module.run_command(['su', '-', 'irods', '-c', 'iadmin addchildtoresc {0} {1}'.format(passthrough_resc, leaf_resc)], check_rc=True)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            username=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    perform_test_setup(module.params['username'], module)

    result = {
        'changed': True,
        'complex_args': module.params,
    }

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
