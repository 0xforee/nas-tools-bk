import json
from datetime import datetime

from app.helper import ChromeHelper, SiteHelper, DbHelper
from app.message import Message
from app.utils import RequestUtils, StringUtils, ExceptionUtils, MteamUtils
from app.utils.commons import singleton
from config import Config
from app.conf import SiteConf
from lxml import etree



@singleton
class Sites:
    message = None
    dbhelper = None

    _sites = []
    _siteByIds = {}
    _siteByUrls = {}
    _site_favicons = {}
    _rss_sites = []
    _brush_sites = []
    _statistic_sites = []
    _signin_sites = []

    _MAX_CONCURRENCY = 10

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.dbhelper = DbHelper()
        self.message = Message()
        # 原始站点列表
        self._sites = []
        # ID存储站点
        self._siteByIds = {}
        # URL存储站点
        self._siteByUrls = {}
        # 开启订阅功能站点
        self._rss_sites = []
        # 开启刷流功能站点：
        self._brush_sites = []
        # 开启统计功能站点：
        self._statistic_sites = []
        # 开启签到功能站点：
        self._signin_sites = []
        # 站点图标
        self.init_favicons()
        # 站点数据
        self._sites = self.dbhelper.get_config_site()
        for site in self._sites:
            # 站点属性
            site_note = self.__get_site_note_items(site.NOTE)
            # 站点用途：Q签到、D订阅、S刷流
            site_rssurl = site.RSSURL
            site_signurl = site.SIGNURL
            site_cookie = site.COOKIE
            site_uses = site.INCLUDE or ''
            uses = []
            if site_uses:
                signin_enable = True if "Q" in site_uses and site_signurl and site_cookie else False
                rss_enable = True if "D" in site_uses and site_rssurl else False
                brush_enable = True if "S" in site_uses and site_rssurl and site_cookie else False
                statistic_enable = True if "T" in site_uses and (site_rssurl or site_signurl) and site_cookie else False
                uses.append("Q") if signin_enable else None
                uses.append("D") if rss_enable else None
                uses.append("S") if brush_enable else None
                uses.append("T") if statistic_enable else None
            else:
                signin_enable = False
                rss_enable = False
                brush_enable = False
                statistic_enable = False
            site_info = {
                "id": site.ID,
                "name": site.NAME,
                "pri": site.PRI or 0,
                "rssurl": site_rssurl,
                "signurl": site_signurl,
                "cookie": site_cookie,
                "rule": site_note.get("rule"),
                "download_setting": site_note.get("download_setting"),
                "signin_enable": signin_enable,
                "rss_enable": rss_enable,
                "brush_enable": brush_enable,
                "statistic_enable": statistic_enable,
                "uses": uses,
                "ua": site_note.get("ua"),
                "parse": True if site_note.get("parse") == "Y" else False,
                "unread_msg_notify": True if site_note.get("message") == "Y" else False,
                "chrome": True if site_note.get("chrome") == "Y" else False,
                "proxy": True if site_note.get("proxy") == "Y" else False,
                "subtitle": True if site_note.get("subtitle") == "Y" else False,
                "strict_url": StringUtils.get_base_url(site_signurl or site_rssurl)
            }
            # 以ID存储
            self._siteByIds[site.ID] = site_info
            # 以域名存储
            site_strict_url = StringUtils.get_url_domain(site.SIGNURL or site.RSSURL)
            if site_strict_url:
                self._siteByUrls[site_strict_url] = site_info

    def init_favicons(self):
        """
        加载图标到内存
        """
        self._site_favicons = {site.SITE: site.FAVICON for site in self.dbhelper.get_site_favicons()}

    def get_sites(self,
                  siteid=None,
                  siteurl=None,
                  rss=False,
                  brush=False,
                  signin=False,
                  statistic=False):
        """
        获取站点配置
        """
        if siteid:
            return self._siteByIds.get(int(siteid)) or {}
        if siteurl:
            return self._siteByUrls.get(StringUtils.get_url_domain(siteurl)) or {}

        ret_sites = []
        for site in self._siteByIds.values():
            if rss and not site.get('rss_enable'):
                continue
            if brush and not site.get('brush_enable'):
                continue
            if signin and not site.get('signin_enable'):
                continue
            if statistic and not site.get('statistic_enable'):
                continue
            ret_sites.append(site)
        if siteid or siteurl:
            return {}
        return ret_sites

    @staticmethod
    def is_public_site(url):
        """
        判断是否为公开BT站点
        """
        _, netloc = StringUtils.get_url_netloc(url)
        if netloc in SiteConf.PUBLIC_TORRENT_SITES.keys():
            return True
        return False

    @staticmethod
    def get_public_sites(url=None):
        """
        查询所有公开BT站点
        """
        if url:
            _, netloc = StringUtils.get_url_netloc(url)
            return SiteConf.PUBLIC_TORRENT_SITES.get(netloc) or {}
        else:
            return SiteConf.PUBLIC_TORRENT_SITES.items()

    def get_sites_by_suffix(self, suffix):
        """
        根据url的后缀获取站点配置
        """
        for key in self._siteByUrls:
            if key.endswith(suffix):
                return self._siteByUrls[key]
        return {}

    def get_site_dict(self,
                      rss=False,
                      brush=False,
                      signin=False,
                      statistic=False):
        """
        获取站点字典
        """
        return [
            {
                "id": site.get("id"),
                "name": site.get("name")
            } for site in self.get_sites(
                rss=rss,
                brush=brush,
                signin=signin,
                statistic=statistic
            )
        ]

    def get_site_names(self,
                       rss=False,
                       brush=False,
                       signin=False,
                       statistic=False):
        """
        获取站点名称
        """
        return [
            site.get("name") for site in self.get_sites(
                rss=rss,
                brush=brush,
                signin=signin,
                statistic=statistic
            )
        ]

    def get_site_favicon(self, site_name=None):
        """
        获取站点图标
        """
        if site_name:
            return self._site_favicons.get(site_name)
        else:
            return self._site_favicons

    def get_site_download_setting(self, site_name=None):
        """
        获取站点下载设置
        """
        if site_name:
            for site in self._siteByIds.values():
                if site.get("name") == site_name:
                    return site.get("download_setting")
        return None

    def parse_site_download_url(self, page_url, xpath):
        """
        从站点详情页面中解析中下载链接
        :param page_url: 详情页面地址
        :param xpath: 解析XPATH，同时还包括Cookie、UA和Referer
        """
        if not page_url or not xpath:
            return ""
        cookie, ua, referer, page_source = None, None, None, None
        xpaths = xpath.split("|")
        xpath = xpaths[0]
        if len(xpaths) > 1:
            cookie = xpaths[1]
        if len(xpaths) > 2:
            ua = xpaths[2]
        if len(xpaths) > 3:
            referer = xpaths[3]
        try:
            site_info = self.get_public_sites(url=page_url)
            if not site_info.get("referer"):
                referer = None
            req = RequestUtils(
                headers=ua,
                cookies=cookie,
                referer=referer,
                proxies=Config().get_proxies() if site_info.get("proxy") else None
            ).get_res(url=page_url)
            if req and req.status_code == 200:
                if req.text:
                    page_source = req.text
            # xpath解析
            if page_source:
                html = etree.HTML(page_source)
                urls = html.xpath(xpath)
                if urls:
                    return str(urls[0])
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
        return None


    def test_connection(self, site_id):
        """
        测试站点连通性
        :param site_id: 站点编号
        :return: 是否连通、错误信息、耗时
        """
        site_info = self.get_sites(siteid=site_id)
        if not site_info:
            return False, "站点不存在", 0
        site_cookie = site_info.get("cookie")
        if not site_cookie:
            return False, "未配置站点Cookie", 0
        ua = site_info.get("ua")
        site_url = StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl"))
        if not site_url:
            return False, "未配置站点地址", 0
        chrome = ChromeHelper()
        if site_info.get("chrome") and chrome.get_status():
            # 计时
            start_time = datetime.now()
            if not chrome.visit(url=site_url, ua=ua, cookie=site_cookie, proxy=site_info.get("proxy")):
                return False, "Chrome模拟访问失败", 0
            # 循环检测是否过cf
            cloudflare = chrome.pass_cloudflare()
            seconds = int((datetime.now() - start_time).microseconds / 1000)
            if not cloudflare:
                return False, "跳转站点失败", seconds
            # 判断是否已签到
            html_text = chrome.get_html()
            if not html_text:
                return False, "获取站点源码失败", 0
            if SiteHelper.is_logged_in(html_text):
                return True, "连接成功", seconds
            else:
                if site_url.find("m-team") != -1:
                    return self.mteam_sign(site_info)
                return False, "Cookie失效", seconds
        else:
            if site_url.find("m-team") != -1:
                return self.mteam_sign(site_info)
            # 计时
            start_time = datetime.now()
            res = RequestUtils(cookies=site_cookie,
                               headers=ua,
                               proxies=Config().get_proxies() if site_info.get("proxy") else None
                               ).get_res(url=site_url)
            seconds = int((datetime.now() - start_time).microseconds / 1000)
            if res and res.status_code == 200:
                if not SiteHelper.is_logged_in(res.text):
                    return False, "Cookie失效", seconds
                else:
                    return True, "连接成功", seconds
            elif res is not None:
                return False, f"连接失败，状态码：{res.status_code}", seconds
            else:
                return False, "无法打开网站", seconds

    def mteam_sign(self, site_info):
        start_time = datetime.now()
        result, reason = MteamUtils.mteam_sign(site_info)
        seconds = int((datetime.now() - start_time).microseconds / 1000)
        return result, reason, seconds

    @staticmethod
    def __get_site_note_items(note):
        """
        从note中提取站点信息
        """
        infos = {}
        if note:
            infos = json.loads(note)
        return infos
