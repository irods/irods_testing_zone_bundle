#!/usr/bin/python

from collections import OrderedDict

class Hosts(object):
    def __init__(self, filename=None):
        entries = OrderedDict()
        if filename is not None:
            with open(filename) as f:
                for line in f:
                    e = self.parse_line(line)
                    if e is not None:
                        ip, hostnames = e
                        try:
                            entries[ip].extend(hostnames)
                        except KeyError:
                            entries[ip] = hostnames
        self.entries = entries
        self.filename = filename

    @staticmethod
    def parse_line(line):
        data = line.split('#')[0]
        ip_and_hostnames = data.split()
        if len(ip_and_hostnames) < 2:
            return None
        return ip_and_hostnames[0], ip_and_hostnames[1:]

    def set_hostnames(self, ip, hostnames):
        self.entries[ip] = hostnames

    def write_to_file(self, filename=None):
        if filename is None:
            filename = self.filename
        with open(filename, 'w') as f:
            for ip, hostnames in self.entries.items():
                f.write('{ip} {hostnames}\n'.format(ip=ip, hostnames=' '.join(hostnames)))

def main():
    module = AnsibleModule(
        argument_spec = dict(
            hosts_file=dict(type='str', required=True),
            ip_address_to_hostnames_dict=dict(type='dict', required=True),
        ),
        required_together=[],
        supports_check_mode=False,
    )

    hosts = Hosts(module.params['hosts_file'])
    for ip_address, hostnames in module.params['ip_address_to_hostnames_dict'].items():
        hosts.set_hostnames(ip_address, hostnames)
    hosts.write_to_file()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
