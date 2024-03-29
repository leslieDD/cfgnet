#!/usr/bin/python3
import sys
import re
import argparse
import ipaddress
import logging
import asyncio
import getpass
from pprint import pprint
from pickletools import uint8
import asyncssh
from termcolor import colored
from atomic import AtomicLong

tmpl_address = "8.8.8.8"
DEBUG = False

logging.basicConfig(level=logging.WARNING,
                    format='%(message)s',
                    datefmt='%Y-%m-%d %M:%S')

__version__ = "0.0.1"


# logging.basicConfig(level=logging.WARNING,
#     format='%(asctime)s [%(lineno)d] %(levelname)s # %(message)s',
#     datefmt='%Y-%m-%d %M:%S')

def example():
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置上地址,会覆盖旧的所有地址', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.200.0/24', 'yellow'))
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置上地址和网关,会覆盖旧的所有地址', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.200.0/24 -g 10.30.200.1', 'yellow'))
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置上地址,会覆盖旧的所有地址,并排除10.30.200.1地址', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.200.0/24 -E 10.30.200.1', 'yellow'))
    print(colored('# 只打印地址对应结果', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.200.0/24 -I', 'yellow'))
    print(colored('# 打印详细的执行结果', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.200.0/24 -D', 'yellow'))
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置网关', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -g 10.30.200.1', 'yellow'))
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置新地址', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.200.0/24 --add', 'yellow'))
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置新地址，没有设定网关，跳过DNS，指定分配起始地址', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -n 10.30.220.0/24 -s 10.30.220.100 -d "-" --add', 'yellow'))
    print(colored('# 给文件hosts中的所有主机 (网关所在网络接口) 配置上ipv6地址,会覆盖旧的所有地址', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -t 6 -n 2201:8aab:7be1:200::/56 -g 2201:8aab:7be1:200::1', 'yellow'))
    print(colored('# 只配置IPV6的DNS', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -t 6', 'yellow'))
    print(colored(f'{sys.argv[0]} -p hosts -t 6 -d "2400:3200::1,2400:3200:baba::1"', 'yellow'))
    print(colored('# 只配置IPV4的DNS', 'blue'))
    print(colored(f'{sys.argv[0]} -p hosts -t 4', 'yellow'))
    print(colored(f'{sys.argv[0]} -p hosts -t 4 -d "114.114.114.114"', 'yellow'))

    print(colored('# 尝试识别文件中的IP地址,排序结果并输出', 'blue'))
    print(colored(f'{sys.argv[0]} -S addr_file', 'yellow'))


def parse_argument():
    parser = argparse.ArgumentParser(
        description='给服务器配置IP地址，IP的地址将会配置到出网网口上或者指定的网口或者连接上\n默认为替换，可以指定增加或者减少\n' +
                    '\033[41;37m在配置IP时，是否考虑加上--add参数，默认配置IP会覆盖原来的IP\033[0m',
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-A', '--askpass', action='store_true', default=False, help="指定SSH密码")
    parser.add_argument('-u', '--user', type=str, default='', metavar='username',
                        help="指定SSH登录的用户名，当在-p指定的地址池中没有明确指定用户名时，使用此用户名")
    parser.add_argument('-p', '--pool', type=str, default='', metavar='filename',
                        help='指定存地址池的文件名，一个IP一行，只支持v4\n格式：[user@]host[:port]\n默认端口号22,用户名为root')
    parser.add_argument('--desc', action='store_true', default=False,
                        help="降序（descending）排列由-A指定的地址池，默认是升序")
    parser.add_argument('--nsort', action='store_true', default=False, help="不排序由-A指定的地址池，默认是升序")
    parser.add_argument('-m', '--manual-asc', type=str, default='', metavar='ipaddress',
                        help="手动指定生成地址的起点，升序生成地址")
    parser.add_argument('--manual-desc', type=str, default='', metavar='ipaddress',
                        help="手动指定生成地址的起点，降序生成地址")
    parser.add_argument('-t', '--type', type=int, default=0, choices=[4, 6],
                        help='指定地址类型，4(=v4)或者6(=v6)，默认根据其它选项的内容进行推测')
    parser.add_argument('-n', '--network', type=str, default='', metavar='network_address',
                        help='指定IP的网段，地址类型必须和选定的类型一致')
    parser.add_argument('-g', '--gateway', type=str, default='', metavar='gateway_address',
                        help='指定IP的网关，地址类型必须和选定的类型一致')
    parser.add_argument('-s', '--start', type=str, default='', metavar='ipaddress',
                        help="起点地址，地址类型必须和选定的类型一致")
    parser.add_argument('-d', '--dns', type=str, default='', metavar='[ipaddress,...]',
                        help='指定DNS地址，以英文逗号分隔\n' +
                             '如果内容为-，则不配置DNS\n' +
                             '为空值时，会根据其它选择的地址类型选定默认的DNS值\n' +
                             '默认v4的DNS是：114.114.114.114,1.2.4.8\n' +
                             '默认v6的DNS是：2001:4860:4860::8888,2001:4860:4860::8844\n' +
                             '阿里v6的DNS是：2400:3200::1,2400:3200:baba::1\n')
    parser.add_argument('-E', '--lexclude', type=str, default='', metavar='[ipaddress,...]',
                        help='生成IP时，从中间排除的IP地址列表，以英文逗号分开')
    parser.add_argument('-F', '--fexclude', type=str, default='', metavar='filename',
                        help='生成IP时，从中间排除的IP地址列表\n从文件读取，一行一个IP')
    parser.add_argument('-e', '--eth', type=str, default='', metavar='eth_name', help="网卡设备名称")
    parser.add_argument('-c', '--cname', type=str, default='', metavar='nmcli_connection_name', help="nmcli的连接名称")
    parser.add_argument('--add', action='store_true', default=False, help="增加")
    parser.add_argument('--sub', action='store_true', default=False, help="减少")
    parser.add_argument('--noup', action='store_true', default=False, help="不执行UP操作")
    parser.add_argument('-C', '--concurrency', type=int, default=6, metavar='number', help="并发数，默认为6")
    parser.add_argument('-I', '--ipaddr', action='store_true', default=False,
                        help="只显示生成的IP地址与地址池（-p）的对应列表\n## 并不执行任务 ##")
    parser.add_argument('-T', '--test', action='store_true', default=False,
                        help="尝试执行指定的简单的命令，并返回结果，并不会执行生成的配置任务")
    parser.add_argument('-S', '--sort', type=str, metavar='filename',
                        help="过滤出指定文件中的IPv4/IPv6，并排序输出后退出程序")
    parser.add_argument('-D', '--debug', action='store_true', default=False, help='输出详细日志')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)
    sub_command = parser.add_subparsers()
    cmd_example = sub_command.add_parser('example', help='显示一些命令使用实例')

    cmd_example.set_defaults(func=example)
    options = parser.parse_args()
    return options


def read(filename):
    try:
        with open(filename, encoding="utf8", mode='r') as fd:
            content = fd.read()
    except Exception as e:
        logging.error("文件打开出错：%s" % e)
        return None
    return content


def check_ipaddr_v6(addr):
    try:
        parsed = ipaddress.ip_address(addr)
        if parsed.version != 6:
            return None
    except Exception as e:
        return None
    return parsed


def check_ipaddr_v4(addr):
    try:
        parsed = ipaddress.ip_address(addr)
        if parsed.version != 4:
            return None
    except Exception as e:
        return None
    return parsed


def check_ipaddr(addr):
    try:
        parsed = ipaddress.ip_address(addr)
    except Exception as e:
        return None
    return parsed


def generate_user(params_parsed):
    if not params_parsed['network']:
        while True:
            yield None
    base_num = params_parsed['base_num']
    base_addr = params_parsed['manual_addr_parsed']

    def gen():
        index = 0
        while True:
            try:
                ipvx_addr = base_addr + index
                index += base_num
                if ipvx_addr >= params_parsed['network'].broadcast_address:
                    break  # 已经超出广播地址
                if ipvx_addr <= params_parsed['network'].network_address:
                    break  # 已经比网络地址更小
                if ipvx_addr == params_parsed['gateway']:
                    continue
                for excludeIP in params_parsed['exclude']:
                    if excludeIP == ipvx_addr:
                        break
                else:
                    yield ipvx_addr
            except:
                break

    yield from gen()
    while True:
        yield None


def generate_addr_v2(params_parsed):
    if not params_parsed['network']:
        while True:
            yield None

    def gen_asc():
        if params_parsed['starting_addr'] is not None:
            base_addr = params_parsed['starting_addr']
        elif params_parsed['gateway'] is not None:
            base_addr = params_parsed['gateway'] + 1
        else:
            base_addr = params_parsed['network'].network_address + 1
        index = 0
        while True:
            try:
                ipvx_addr = base_addr + index
                index += 1
                if ipvx_addr >= params_parsed['network'].broadcast_address:
                    break  # 已经超出广播地址
                if ipvx_addr == params_parsed['gateway']:
                    continue
                for excludeIP in params_parsed['exclude']:
                    if excludeIP == ipvx_addr:
                        break
                else:
                    yield ipvx_addr
            except:
                break

    def gen_desc():
        if params_parsed['starting_addr'] is not None:
            base_addr = params_parsed['starting_addr']
        elif params_parsed['gateway'] is not None:
            base_addr = params_parsed['gateway'] + 1
        else:
            base_addr = params_parsed['network'].broadcast_address - 1
        index = 0
        while True:
            try:
                ipvx_addr = base_addr - index
                index += 1
                if ipvx_addr <= params_parsed['network'].network_address:
                    break  # 已经比网络地址更小
                if ipvx_addr == params_parsed['gateway']:
                    continue
                for excludeIP in params_parsed['exclude']:
                    print(str(excludeIP), str(ipvx_addr))
                    if excludeIP == ipvx_addr:
                        break
                else:
                    yield ipvx_addr
            except:
                break

    if params_parsed['network'].network_address + 1 == params_parsed['gateway']:
        yield from gen_asc()
    elif params_parsed['network'].broadcast_address - 1 == params_parsed['gateway']:
        yield from gen_desc()
    else:
        yield from gen_asc()
        yield from gen_desc()

    while True:
        yield None


def generate_addr_v1(params_parsed):
    if not params_parsed['network']:
        while True:
            yield None

    if params_parsed['starting_addr'] is not None:
        base_addr = params_parsed['starting_addr']
    else:
        base_addr = params_parsed['network'].network_address + 1
    index = 0
    while True:
        ipvx_addr = base_addr + index
        index += 1
        if ipvx_addr == params_parsed['gateway'] or ipvx_addr == params_parsed['network'].broadcast_address:
            continue
        elif ipvx_addr > params_parsed['network'].broadcast_address:
            break
        for excludeIP in params_parsed['exclude']:
            if excludeIP == ipvx_addr:
                continue
        yield ipvx_addr
    while True:
        yield None


def parsed_params(args):
    global DEBUG
    DEBUG = args.debug

    if DEBUG:
        pprint(args)

    if args.concurrency == 0:
        logging.error("消费工作协程数必须大于等于1")
        return

    if args.add is True and args.sub is True:
        logging.error("--add和--sub不能同时存在，只能选择其中一个")
        return

    if args.cname != '' and args.eth != '':
        logging.error("--eth和--cname不能同时存在，只能选择其中一个")
        return

    params_parsed = {
        'device': args.eth,
        'cname': args.cname,
        'net_type': args.type,
        'add': args.add,
        'sub': args.sub,
        'askpass': args.askpass,
        'display_ipaddr': args.ipaddr,
        'order': args.desc,
        'nsort': args.nsort,
        'manual_addr_parsed': None,
        'user': args.user.strip(),
        'test_cmd': args.test,
        'manual_addr': '',
        'no_up': args.noup,
    }

    if args.pool is None:
        logging.error("需要指定地址池文件，请使用-p指定")
        return
    if args.pool == '':
        logging.error("指定了一个无效的地址池文件，请使用-p指定")
        return

    manual_asc = args.manual_asc.strip()
    manual_desc = args.manual_desc.strip()
    if manual_asc != '' and manual_desc != '':
        logging.error("--manual-asc和--manual-desc不能同时存在，只能选择其中一个")
        return

    exclude = []

    def do_exclude(exclude_param, do_read):
        if exclude_param is None or exclude_param == '':
            return
        if do_read:
            exclude_pool = read(exclude_param)
        else:
            exclude_pool = exclude_param
        if exclude_pool is None:
            return
        for exc_ip in exclude_pool.split():
            exc_ip = exc_ip.strip()
            if exc_ip == "":
                continue
            parsed_inner = check_ipaddr(exc_ip)
            if parsed_inner is None:
                logging.error("指定的排除地址不是合法的IP地址：%s" % exc_ip)
                return False
            if parsed_inner.version != params_parsed['net_type']:
                logging.error("指定的排除地址类型必须一致：%s" % str(parsed_inner))
                return False
            exclude.append(parsed_inner)

    pool_content = read(args.pool)
    if pool_content is None:
        return
    pool_hosts = {}
    for row in pool_content.split("\n"):  # v4地址
        row = row.strip()
        if row == "" or row.startswith("#"):
            continue
        if len(row.split()) != 1:
            continue
        c_host, c_port, c_user = parse_host(row)
        ip_parsed = check_ipaddr_v4(c_host)
        if ip_parsed is None:
            logging.error("指定池{}中的IP不合法: {}".format(args.pool, c_host))
            return
        if c_host not in pool_hosts:
            if c_user == '':
                if params_parsed['user'] != '':
                    c_user = params_parsed['user']
                else:
                    c_user = 'root'
            pool_hosts[c_host] = {
                'host': c_host,
                'port': c_port,
                'user': c_user,
                "host_parsed": ip_parsed,
            }
    if len(pool_hosts) == 0:
        logging.warning("池中没有IP地址")
        return
    pool_parsed = {}
    for _, val in pool_hosts.items():
        pool_parsed[val['host_parsed']] = val
    pool_parsed_sorted = []
    if params_parsed['nsort']:
        tmp_pool_data = pool_parsed
    else:
        tmp_pool_data = sorted(pool_parsed, reverse=params_parsed['order'])
    for item in tmp_pool_data:
        pool_parsed_sorted.append(pool_parsed[item])
    params_parsed['pool'] = pool_parsed_sorted

    network = args.network
    if network is not None and network != '':
        if "/" not in network:
            logging.error("指定的网段必须包含掩码")
            return
        try:
            network_parsed = ipaddress.ip_network(network.strip())
            if params_parsed['net_type'] == 0:
                params_parsed['net_type'] = network_parsed.version
            elif params_parsed['net_type'] != network_parsed.version:
                raise
        except Exception as e:
            logging.error("网段要求是合法的IPv{}网段地址，并且地址类型必须一致".format(params_parsed['net_type']))
            return
        params_parsed['network'] = network_parsed
    else:
        params_parsed['network'] = None

    gateway = args.gateway
    if gateway is not None and gateway != '':
        try:
            gateway_parsed = check_ipaddr(gateway.strip())
            if params_parsed['net_type'] == 0:
                params_parsed['net_type'] = gateway_parsed.version
            elif params_parsed['net_type'] != gateway_parsed.version:
                raise
        except Exception as e:
            logging.error("网关要求是合法的IPv{}地址，并且地址类型必须一致".format(params_parsed['net_type']))
            return
        if params_parsed['network'] is not None and gateway_parsed not in params_parsed['network']:
            logging.error("网关不在指定的网段中")
            return
        params_parsed['gateway'] = gateway_parsed
    else:
        params_parsed['gateway'] = None

    starting_addr_entry = args.start
    if starting_addr_entry is not None and starting_addr_entry != "":
        try:
            starting_addr = check_ipaddr(starting_addr_entry.strip())
            if params_parsed['net_type'] == 0:
                params_parsed['net_type'] = starting_addr.version
            elif params_parsed['net_type'] != starting_addr.version:
                raise
        except Exception as e:
            logging.error("起点地址要求是合法的IPv{}地址，并且地址类型必须一致".format(params_parsed['net_type']))
            return
        if params_parsed['network'] is not None and starting_addr not in params_parsed['network']:
            logging.error("起点地址不在指定的网段中")
            return
        params_parsed['starting_addr'] = starting_addr
    else:
        params_parsed['starting_addr'] = None

    if manual_asc != '':
        params_parsed['manual_addr'] = manual_asc
        params_parsed['base_num'] = 1
    elif manual_desc != '':
        params_parsed['manual_addr'] = manual_desc
        params_parsed['base_num'] = -1
    else:
        params_parsed['base_num'] = 1

    if params_parsed['manual_addr'] != '':
        try:
            manual_addr_parsed = check_ipaddr(params_parsed['manual_addr'])
            if params_parsed['net_type'] == 0:
                params_parsed['net_type'] = manual_addr_parsed.version
            elif params_parsed['net_type'] != manual_addr_parsed.version:
                raise
        except Exception as e:
            logging.error("手动指定的地址要求是合法的IPv{}地址，并且地址类型必须一致".format(params_parsed['net_type']))
            return
        if params_parsed['network'] is not None and manual_addr_parsed not in params_parsed['network']:
            logging.error("手动指定的地址不在指定的网段中")
            return
        params_parsed['manual_addr_parsed'] = manual_addr_parsed
    else:
        params_parsed['manual_addr_parsed'] = None

    if args.dns is not None and args.dns != "-":
        if args.dns == "":
            if params_parsed['net_type'] == 6:
                dns_addrs = '2001:4860:4860::8888,2001:4860:4860::8844'
            elif params_parsed['net_type'] == 4:
                dns_addrs = '114.114.114.114,1.2.4.8'
            else:
                logging.error("没有指定网络类型")
                return
        else:
            dns_addrs = args.dns.strip()
        dns_check = []
        if " " in dns_addrs:
            dns_addrs_pool = dns_addrs.split()
        else:
            dns_addrs_pool = dns_addrs.split(",")
        for dns in dns_addrs_pool:
            dns = dns.strip()
            if dns == "":
                continue
            try:
                parsed = check_ipaddr(dns.strip())
                if params_parsed['net_type'] == 0:
                    params_parsed['net_type'] = parsed.version
                elif params_parsed['net_type'] != parsed.version:
                    raise
            except Exception as e:
                logging.error("提供DNS地址要求是v{}版本，地址类型必须一致".format(params_parsed['net_type']))
                return
            dns_check.append(dns)
        params_parsed['dns'] = ' '.join(dns_check)
    else:
        params_parsed['dns'] = None

    if do_exclude(args.lexclude, False) is False:
        return
    if do_exclude(args.fexclude, True) is False:
        return
    params_parsed['exclude'] = exclude

    if args.askpass:
        password = getpass.getpass('Password:')
        params_parsed['password'] = password
    else:
        params_parsed['password'] = None

    if DEBUG:
        pprint(params_parsed)
    return params_parsed


def parse_host(host, default_user='', default_port=22):
    """
    Parses host entries of the form "[user@]host[:port]".
    """
    user = default_user
    port = default_port
    if '@' in host:
        user, host = host.split('@', 1)
    if ':' in host:
        host, port = host.rsplit(':', 1)
    return host, port, user


def generate_tasks(params_parsed):
    """
    脚本功能：
    1. 为每台机器配置v4/v6版本的IP地址，网关，DNS，以及以上三者之间的任意组合
    2. 当参数中提供了网段时，就认为有机器配置IP地址，
    """
    cfg_ipaddr = False
    if params_parsed['network']:
        cfg_ipaddr = True
        prefix_len = params_parsed['network'].prefixlen
    else:
        if params_parsed['net_type'] == 6:
            prefix_len = 128
        elif params_parsed['net_type'] == 4:
            prefix_len = 32
        else:
            prefix_len = 32
    if params_parsed['manual_addr_parsed']:
        gen_addr = generate_user(params_parsed)
    else:
        gen_addr = generate_addr_v2(params_parsed)
    for host_info in params_parsed['pool']:
        ipvx_addr = next(gen_addr)
        if cfg_ipaddr and ipvx_addr is None:
            logging.error("提供的网段不够为所有主机分配IP地址")
            break
        task = {
            "address": host_info['host_parsed'],
            "ip_address": ipvx_addr,
            "ip_netmask": prefix_len,
            "ip_gateway": params_parsed['gateway'],
            "ip_dns": params_parsed['dns'],
            "device": params_parsed['device'],  # 将要在此接口上配置IP地址
            "connection": params_parsed['cname'],
            "net_type": params_parsed['net_type'],
            "is_add": params_parsed['add'],
            "is_sub": params_parsed['sub'],
            "uuid": "",
            "cmd_result": "",
            "cmd_stderr": "",
            "cmd_status": False,
            "cmd": [],
            "ssh_info": host_info,
            "ssh_password": params_parsed['password'],
            "cfg_ipaddr": cfg_ipaddr,
            "test_cmd": params_parsed['test_cmd'],
            # "params_parsed": params_parsed
            "no_up": params_parsed['no_up'],
        }
        yield task
    while True:
        yield None


async def run_command(conn, cmd, task):
    try:
        cmd_resp = await conn.run(cmd)
        if cmd_resp.returncode == 0:
            task['cmd_result'] = str(cmd_resp.stdout)
            task['cmd_status'] = True
        else:
            task['cmd_stderr'] = str(cmd_resp.stderr)
            task['cmd_status'] = False
    except asyncssh.ChannelOpenError as e:
        task['cmd_stderr'] = str(e)
        task['cmd_status'] = False
    except asyncssh.TimeoutError as e:
        task['cmd_stderr'] = str(e)
        task['cmd_status'] = False
    except asyncssh.ProcessError as e:
        task['cmd_stderr'] = str(e)
        task['cmd_status'] = False
    except Exception as e:
        task['cmd_stderr'] = str(e)
        task['cmd_status'] = False


async def do_remote_job(task):
    kwargs = {
        'username': task['ssh_info']['user'],
        'password': task['ssh_password'],
        'port': int(task['ssh_info']['port']),
        'known_hosts': None,
        # 'client_keys': [],
    }
    if task['ssh_password']:
        kwargs['client_keys'] = None
    async with await asyncio.wait_for(asyncssh.connect(str(task['address']), **kwargs), timeout=15) as conn:
        if task['test_cmd']:
            await run_command(conn, 'uptime', task)
            return
        if task['connection'] is not None and task['connection'] != '':
            nmcli_tags = task['connection']
        else:
            if task['device'] is not None and task['device'] != '':
                cmd = 'nmcli device connect "{}"'.format(task['device'])
            else:
                cmd = "ip route get " + tmpl_address
                task['cmd'].append(cmd)
                await run_command(conn, cmd, task)
                if task['cmd_status'] is False:
                    return
                fields = task['cmd_result'].split()
                if len(fields) < 5:
                    task['cmd_stderr'] = "cmd response is error"
                    task['cmd_status'] = False
                    return
                task['device'] = fields[4]
                cmd = 'nmcli device connect "{}"'.format(task['device'])
            task['cmd'].append(cmd)
            await run_command(conn, cmd, task)
            try:
                conn_uuid = task['cmd_result'].split()[-1].strip(".").strip("'")
            except:
                task['cmd_stderr'] = "get connection uuid of device %s error: %s" % (task['device'], task['cmd_stderr'])
                task['cmd_status'] = False
                return
            if not re.match(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', conn_uuid):
                task['cmd_stderr'] = "get connection uuid of device %s  error: %s" % (
                    task['device'], task['cmd_stderr'])
                task['cmd_status'] = False
                return
            task['uuid'] = conn_uuid
            nmcli_tags = conn_uuid
        if task['net_type'] == 6:
            net_type = "ipv6"
        elif task['net_type'] == 4:
            net_type = "ipv4"
        else:
            task['cmd_stderr'] = "unknow net type: {}".format(task['net_type'])
            task['cmd_status'] = False
            return
        net_type_action = net_type
        if task['is_add']:
            net_type_action = "+" + net_type
        elif task['is_sub']:
            net_type_action = "-" + net_type
        cmd_unfinished = [
            f'nmcli connection modify "{nmcli_tags}" {net_type}.method manual',
        ]
        if task['ip_address']:
            if task['ip_netmask']:
                cmd_unfinished.append(
                    '{}.addresses "{}/{}"'.format(net_type_action, str(task['ip_address']), task['ip_netmask']))
            else:
                cmd_unfinished.append('{}.addresses "{}"'.format(net_type_action, str(task['ip_address'])))
        if task['ip_gateway']:
            cmd_unfinished.append('{}.gateway "{}"'.format(net_type_action, task['ip_gateway']))
        if task['ip_dns']:
            cmd_unfinished.append('{}.dns "{}"'.format(net_type_action, task['ip_dns']))
        if len(cmd_unfinished) == 1:
            task['cmd_stderr'] = "cmd incomplete, skip"
            task['cmd_status'] = False
            return
        cmd = ' '.join(cmd_unfinished)
        task['cmd'].append(cmd)
        await run_command(conn, cmd, task)
        if task['cmd_status'] is False:
            return
        cmd = 'nmcli connection reload'
        task['cmd'].append(cmd)
        await run_command(conn, cmd, task)
        if task['cmd_status'] is False:
            return
        if not task['no_up']:
            cmd = 'nmcli connection up "{}"'.format(nmcli_tags)
            task['cmd'].append(cmd)
            await run_command(conn, cmd, task)


async def task_producer(ato_task, task_queue, params_parsed):
    for task in generate_tasks(params_parsed):
        if task is None:
            break
        if params_parsed['display_ipaddr'] is True:
            logging.warning("{} => {}".format(str(task['address']), str(task['ip_address'])))
            continue
        await task_queue.put(task)
    ato_task += 1


async def task_customer(ato_task, ato_result, task_queue, result_queue):
    while True:
        try:
            task = task_queue.get_nowait()
        except asyncio.QueueEmpty:
            if ato_task.value != 0:
                break
            await asyncio.sleep(0.1)
            continue
        task_queue.task_done()
        try:
            await do_remote_job(task)
        except (OSError, asyncssh.Error) as exc:
            task['cmd_stderr'] = str(exc)
            task['cmd_status'] = False
        except asyncio.TimeoutError as terr:
            task['cmd_stderr'] = "coroutine wait timeout [15s]"
            task['cmd_status'] = False
        except Exception as e:
            task['cmd_stderr'] = str(e)
            task['cmd_status'] = False
        await result_queue.put(task)
    ato_result += 1


async def task_display(ato_result, customer_num, result_queue):
    global DEBUG
    while True:
        try:
            result = result_queue.get_nowait()
        except asyncio.QueueEmpty:
            if ato_result.value == customer_num:
                break
            await asyncio.sleep(0.1)
            continue
        if DEBUG is True:
            print("target: \033[46;37m{}\x1b[0m ".format(result['address']))
            pprint(result)
            continue
        if result['cmd_status']:
            if result['test_cmd']:
                logging.warning(
                    "target: \x1b[32m{}\x1b[0m, ip: \x1b[32m{}/{}\x1b[0m, status: \x1b[34m{}\x1b" +
                    "[0m, stdout: \x1b[32m{}\x1b[0m, stderr: \x1b[91m{}\x1b[0m".format(
                        str(result['address']),
                        str(result['ip_address']),
                        result['ip_netmask'],
                        result['cmd_status'],
                        result['cmd_result'].strip(),
                        result['cmd_stderr'].strip(),
                    ))
            elif result['cfg_ipaddr']:
                logging.warning("target: \x1b[32m{}\x1b[0m, ip: \x1b[32m{}/{}\x1b[0m, status: \x1b[34m{}\x1b[0m".format(
                    str(result['address']),
                    str(result['ip_address']),
                    result['ip_netmask'],
                    result['cmd_status'],
                ))
            else:
                logging.warning("target: \x1b[32m{}\x1b[0m, status: \x1b[34m{}\x1b[0m".format(
                    str(result['address']),
                    result['cmd_status'],
                ))
        else:
            logging.warning("target: \x1b[32m{}\x1b[0m, status: \x1b[33m{}\x1b[0m, error: \x1b[91m{}\x1b[0m".format(
                str(result['address']),
                result['cmd_status'],
                result['cmd_stderr'].strip(),
            ))
        result_queue.task_done()


async def work(loop, params_parsed, customer_num: uint8):
    task_queue = asyncio.Queue(maxsize=100)
    result_queue = asyncio.Queue(maxsize=100)

    ato_task = AtomicLong(0)
    ato_result = AtomicLong(0)

    coroutines = [loop.create_task(task_producer(ato_task, task_queue, params_parsed))]

    for _ in range(customer_num):
        coroutines.append(loop.create_task(task_customer(ato_task, ato_result, task_queue, result_queue)))
    coroutines.append(loop.create_task(task_display(ato_result, customer_num, result_queue)))

    done, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_EXCEPTION)
    for d in done:
        if d.exception():
            d.print_stack()
    for p in pending:
        p.cancel()


def sorted_ipaddres(sorted_file):
    content = read(sorted_file)
    if not content:
        return content
    ipv4 = {}
    ipv6 = {}
    addrs_like = re.findall(
        r"(?<![:.\w])(?:[a-f0-9]{1,4}:){7}[a-f0-9]{1,4}(?![:.\w])|(?<![.\d])(?:\d{1,3}\.){3}\d{1,3}(?![.\d])",
        content, re.I)
    for addr_like in addrs_like:
        ip_parsed = check_ipaddr(addr_like.strip())
        if not ip_parsed:
            continue
        if ip_parsed.version == 4:
            ipv4[str(ip_parsed)] = ip_parsed
        elif ip_parsed.version == 6:
            ipv6[str(ip_parsed)] = ip_parsed

    ipv4_merge = []
    ipv6_merge = []
    for _, ip_parsed in ipv4.items():
        ipv4_merge.append(ip_parsed)
    for _, ip_parsed in ipv6.items():
        ipv6_merge.append(ip_parsed)
    ipv4_sorted = sorted(ipv4_merge)
    ipv6_sorted = sorted(ipv6_merge)
    for ip_parsed in ipv4_sorted:
        print(str(ip_parsed))
    for ip_parsed in ipv6_sorted:
        print(str(ip_parsed))
    return True


def do():
    args = parse_argument()
    if hasattr(args, 'func'):
        args.func()
        return True
    if args.sort:
        return sorted_ipaddres(args.sort)
    params_parsed = parsed_params(args)
    if not params_parsed:
        return
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    try:
        event_loop.run_until_complete(work(event_loop, params_parsed, args.concurrency))
    except Exception as e:
        logging.error("asyncio error: %s" % e)
    finally:
        event_loop.close()
    return True


if __name__ == "__main__":
    if do():
        sys.exit(0)
    else:
        sys.exit(1)
