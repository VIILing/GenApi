import os
import shutil
from utils import ThreadSafeCookieManagerClass

import yaml

CHAT_REQ_TOKEN = "abc123"
HTTP_PROXY = ""
CF_PROXY_URL = ""
CookieManager = ThreadSafeCookieManagerClass.load_cookies_from_files()

# 管理页面可查阅用户组
ViewerUser: dict[bytes, bytes] = {}

# 管理页面可管理用户组
AdminUser: dict[bytes, bytes] = {}


def __parse():

    if 'config.yaml' not in os.listdir('.'):
        shutil.copy('config-template.yaml', 'config.yaml')

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    global CHAT_REQ_TOKEN, HTTP_PROXY, CF_PROXY_URL

    if config.get('token'):
        CHAT_REQ_TOKEN = config['token']
    if config.get('httpProxy'):
        HTTP_PROXY = config['httpProxy']
    if config.get('cfProxyUrl'):
        CF_PROXY_URL = config['cfProxyUrl']

    if config.get('viewerGroup'):
        for user in config['viewerGroup']:
            ViewerUser[user[0].encode()] = user[1].encode()
    if config.get('adminGroup'):
        for user in config['adminGroup']:
            AdminUser[user[0].encode()] = user[1].encode()
    for k, v in AdminUser.items():
        ViewerUser[k] = v


__parse()