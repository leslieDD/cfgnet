### 功能说明：

批量在线配置IP、网关、DNS，支持v4/v6

#### 使用帮助信息：

```bash
usage: cfgnet [-h] [-A] [-p POOL] [-t {4,6}] [-n NETWORK] [-g GATEWAY] [-s START] [-d DNS] [-E LEXCLUDE] [-F FEXCLUDE] [-e ETH] [-c CNAME] [--add] [--sub] [-C CONCURRENCY] [-S SORT] [-D]

给服务器配置IP地址，IP的地址将会配置到出网网口上或者指定的网口或者连接上
默认为替换，可以指定增加或者减少

optional arguments:
  -h, --help            show this help message and exit
  -A, --askpass         指定SSH密码
  -p POOL, --pool POOL  指定存地址池的文件名，一个IP一行，只支持v4
  -t {4,6}, --type {4,6}
                        指定地址类型，4(=v4)或者6(=v6)，默认根据其它选项的内容进行推测
  -n NETWORK, --network NETWORK
                        指定IP的网段，地址类型必须和选定的类型一致
  -g GATEWAY, --gateway GATEWAY
                        指定IP的网关，地址类型必须和选定的类型一致
  -s START, --start START
                        起点地址，地址类型必须和选定的类型一致
  -d DNS, --dns DNS     指定DNS地址，以英文逗号分隔
                        如果内容为-，则不配置DNS
                        为空值时，会根据其它选择的地址类型选定默认的DNS值
                        默认v4的DNS是：114.114.114.114,1.2.4.8
                        默认v6的DNS是：2001:4860:4860::8888,2001:4860:4860::8844
  -E LEXCLUDE, --lexclude LEXCLUDE
                        生成IP时，从中间排除的IP地址列表，以英文逗号分开
  -F FEXCLUDE, --fexclude FEXCLUDE
                        生成IP时，从中间排除的IP地址列表
                        从文件读取，一行一个IP
  -e ETH, --eth ETH     网卡设备名称
  -c CNAME, --cname CNAME
                        nmcli的连接名称
  --add                 增加
  --sub                 减少
  -C CONCURRENCY, --concurrency CONCURRENCY
                        并发数，默认为6
  -S SORT, --sort SORT  过滤出指定文件中的IPv4/IPv6，并排序输出后退出程序
  -D, --debug           输出详细日志
```

#### 使用范例

##### 配置IPV4

```bash
root@diandianpc:/ipv6# ./cfgnet -p nodes -n 192.168.122.0/24 -s 192.168.122.10  -d '' --add
2022-09-29 50:38 [591] WARNING # Target: 10.10.30.10, IP: 192.168.122.11/24, Status: True
2022-09-29 50:38 [591] WARNING # Target: 10.10.30.20, IP: 192.168.122.12/24, Status: True
2022-09-29 50:38 [591] WARNING # Target: 10.10.40.10, IP: 192.168.122.13/24, Status: True
2022-09-29 50:38 [591] WARNING # Target: 10.10.40.20, IP: 192.168.122.14/24, Status: True
2022-09-29 50:52 [603] WARNING # Target: 1.1.1.1, Status: False, Error: coroutine wait timeout [15s]
```

##### 批量配置ipv6


