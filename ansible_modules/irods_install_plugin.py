#!/usr/bin/python

class PluginInstaller(object):
    def __init__(self, module):
        self.module = module
        self.irods_plugin_packages_directory = module.params['irods_plugin_packages_directory']

    def install(self):
        self.install_plugin()
        self.setup_python_rule_engine()
        
    def install_plugin(self):
        plugin_dir = os.path.join(self.irods_plugin_packages_directory, get_irods_platform_string())
        install_os_packages_from_files([os.path.join(plugin_dir, entry) for entry in os.listdir(plugin_dir)])

    def setup_python_rule_engine(self):
        self.module.run_command(['sudo', 'su', '-', 'irods', '-c', 'python2 scripts/setup_python_rule_engine_as_only_rule_engine.py'], check_rc=True)
    
   
def main():
    module = AnsibleModule(
        argument_spec = dict(
            irods_plugin_packages_directory=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    installer = PluginInstaller(module)
    installer.install()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
