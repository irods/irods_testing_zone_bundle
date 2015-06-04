#!/usr/bin/python

import json

def main():
    module = AnsibleModule(
        argument_spec = dict(
            filename=dict(type='str', required=True),
            update_dict=dict(type='dict', required=True),
        ),
        supports_check_mode=False,
    )

    with open(module.params['filename']) as f:
        dct = json.load(f)
    dct.update(module.params['update_dict'])
    with open(module.params['filename'], 'w') as f:
        json.dump(dct, f, indent=4, sort_keys=True)

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
