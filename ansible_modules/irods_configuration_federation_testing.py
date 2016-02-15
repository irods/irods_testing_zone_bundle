#!/usr/bin/python

def create_user(username, module):
    module.run_command(['su', '-', 'irods', '-c', 'iadmin mkuser {0} rodsuser'.format(username)], check_rc=True)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            username=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    create_user(module.params['username'], module)
    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
