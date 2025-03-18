from utils import ThreadSafeCookieManagerClass

CHAT_REQ_TOKEN = "abc123"
TEXT_BEFORE_PROMPT = ""
TEXT_AFTER_PROMPT = ""
KEEP_CHAT = False
IGNORE_THINKING = False
HTTP_PROXY = ""
CF_PROXY_URL = ""
CookieManager = ThreadSafeCookieManagerClass.load_cookies_from_files()

# 管理页面可查阅用户组
ViewerUser: dict[bytes, bytes] = {}

# 管理页面可管理用户组
AdminUser: dict[bytes, bytes] = {}