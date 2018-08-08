#!/usr/bin/python

def main():
    module = AnsibleModule(
        argument_spec = dict(
            ssh_config_file=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    with open(module.params['ssh_config_file'], 'a+') as f:
         f.write('    StrictHostKeyChecking no\n')
         f.write('    UserKnownHostsFile /dev/null\n')
         f.write('    LogLevel QUIET\n')

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
