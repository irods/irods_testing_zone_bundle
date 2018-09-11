#!/usr/bin/python

def main():
    module = AnsibleModule(
        argument_spec = dict(
            server_host_name=dict(type='str', required=True),
            server_ip_address=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    module.run_command(['sudo', 'su', '-', 'irods', '-c', 'ssh-keyscan -t ecdsa -H {0},{1} >> .ssh/known_hosts'.format(module.params['server_host_name'], module.params['server_ip_address'])], check_rc=True)    
    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
