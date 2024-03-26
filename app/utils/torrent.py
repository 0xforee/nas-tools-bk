import datetime
import os.path
import re
from urllib.parse import quote, unquote, urlparse

from bencode import bdecode

from app.utils.mteam_utils import MteamUtils
from app.utils.http_utils import RequestUtils
from app.utils.types import MediaType
from config import Config

# Trackers列表
trackers = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://9.rarbg.com:2810/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "https://opentracker.i2p.rocks:443/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker1.bt.moack.co.kr:80/announce",
    "udp://tracker.pomf.se:80/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://movies.zsw.ca:6969/announce",
    "udp://ipv4.tracker.harry.lu:80/announce",
    "udp://explodie.org:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "https://tracker.nanoha.org:443/announce",
    "https://tracker.lilithraws.org:443/announce",
    "https://tr.burnabyhighstar.com:443/announce",
    "http://tracker.mywaifu.best:6969/announce",
    "http://bt.okmp3.ru:2710/announce"
]

class Torrent:
    _torrent_temp_path = None

    def __init__(self):
        self._torrent_temp_path = Config().get_temp_path()
        if not os.path.exists(self._torrent_temp_path):
            os.makedirs(self._torrent_temp_path)

    def get_torrent_info(self, url, cookie=None, ua=None, referer=None, proxy=False):
        """
        把种子下载到本地，返回种子内容
        :param url: 种子链接
        :param cookie: 站点Cookie
        :param ua: 站点UserAgent
        :param referer: 关联地址，有的网站需要这个否则无法下载
        :param proxy: 是否使用内置代理
        :return: 种子保存路径、种子内容、种子文件列表主目录、种子文件列表、错误信息
        """
        if not url:
            return None, None, "", [], "URL为空"
        if url.startswith("magnet:"):
            return None, url, "", [], f"{url} 为磁力链接"
        try:
            # 下载保存种子文件
            file_path, content, errmsg = self.save_torrent_file(url=url,
                                                                cookie=cookie,
                                                                ua=ua,
                                                                referer=referer,
                                                                proxy=proxy)
            if not file_path:
                return None, content, "", [], errmsg
            # 解析种子文件
            files_folder, files, retmsg = self.get_torrent_files(file_path)
            # 种子文件路径、种子内容、种子文件列表主目录、种子文件列表、错误信息
            return file_path, content, files_folder, files, retmsg

        except Exception as err:
            return None, None, "", [], "下载种子文件出现异常：%s" % str(err)

    def save_torrent_file(self, url, cookie=None, ua=None, referer=None, proxy=False):
        """
        把种子下载到本地
        :return: 种子保存路径，错误信息
        """
        if url.find("m-team") != -1:
            url = MteamUtils.get_mteam_url(url, cookie, ua, referer, proxy)
            if not url:
                return None, url, f"mteam 种子链接获取出错，详情地址为 {url}"
            req = MteamUtils.buildRequestUtils(
                headers=ua,
                cookies=cookie,
                referer=referer,
                proxies=Config().get_proxies() if proxy else None
            ).get_res(url=url, allow_redirects=False)
        else:
            req = RequestUtils(
                headers=ua,
                cookies=cookie,
                referer=referer,
                proxies=Config().get_proxies() if proxy else None
            ).get_res(url=url, allow_redirects=False)
        while req and req.status_code in [301, 302]:
            url = req.headers['Location']
            if url and url.startswith("magnet:"):
                return None, url, f"获取到磁力链接：{url}"
            req = RequestUtils(
                headers=ua,
                cookies=cookie,
                referer=referer,
                proxies=Config().get_proxies() if proxy else None
            ).get_res(url=url, allow_redirects=False)
        if req and req.status_code == 200:
            if not req.content:
                return None, None, "未下载到种子数据"
            # 解析内容格式
            if req.text and str(req.text).startswith("magnet:"):
                return None, req.text, "磁力链接"
            else:
                try:
                    bdecode(req.content)
                except Exception as err:
                    print(str(err))
                    return None, None, "种子数据有误，请确认链接是否正确，如为PT站点则需手工在站点下载一次种子"
            # 读取种子文件名
            file_name = self.__get_url_torrent_filename(req, url)
            # 种子文件路径
            file_path = os.path.join(self._torrent_temp_path, file_name)
            # 种子内容
            file_content = req.content
            # 写入磁盘
            with open(file_path, 'wb') as f:
                f.write(file_content)
        elif req is None:
            return None, None, "无法打开链接：%s" % url
        else:
            return None, None, "下载种子出错，状态码：%s" % req.status_code

        return file_path, file_content, ""

    @staticmethod
    def convert_hash_to_magnet(hash_text, title):
        """
        根据hash值，转换为磁力链，自动添加tracker
        :param hash_text: 种子Hash值
        :param title: 种子标题
        """
        if not hash_text or not title:
            return None
        hash_text = re.search(r'[0-9a-z]+', hash_text, re.IGNORECASE)
        if not hash_text:
            return None
        hash_text = hash_text.group(0)
        ret_magnet = f'magnet:?xt=urn:btih:{hash_text}&dn={quote(title)}'
        for tracker in trackers:
            ret_magnet = f'{ret_magnet}&tr={quote(tracker)}'
        return ret_magnet

    @staticmethod
    def add_trackers_to_magnet(url, title=None):
        """
        添加tracker和标题到磁力链接
        """
        if not url or not title:
            return None
        ret_magnet = url
        if title and url.find("&dn=") == -1:
            ret_magnet = f'{ret_magnet}&dn={quote(title)}'
        for tracker in trackers:
            ret_magnet = f'{ret_magnet}&tr={quote(tracker)}'
        return ret_magnet

    @staticmethod
    def get_torrent_files(path):
        """
        解析Torrent文件，获取文件清单
        :return: 种子文件列表主目录、种子文件列表、错误信息
        """
        if not path or not os.path.exists(path):
            return "", [], f"种子文件不存在：{path}"
        file_names = []
        file_folder = ""
        try:
            torrent = bdecode(open(path, 'rb').read())
            if torrent.get("info"):
                files = torrent.get("info", {}).get("files") or []
                if files:
                    for item in files:
                        if item.get("path"):
                            file_names.append(item["path"][0])
                    file_folder = torrent.get("info", {}).get("name")
                else:
                    file_names.append(torrent.get("info", {}).get("name"))
        except Exception as err:
            return file_folder, file_names, "解析种子文件异常：%s" % str(err)
        return file_folder, file_names, ""

    def read_torrent_content(self, path):
        """
        读取本地种子文件的内容
        :return: 种子内容、种子文件列表主目录、种子文件列表、错误信息
        """
        if not path or not os.path.exists(path):
            return None, "", [], "种子文件不存在：%s" % path
        content, retmsg, file_folder, files = None, "", "", []
        try:
            # 读取种子文件内容
            with open(path, 'rb') as f:
                content = f.read()
            # 解析种子文件
            file_folder, files, retmsg = self.get_torrent_files(path)
        except Exception as e:
            retmsg = "读取种子文件出错：%s" % str(e)
        return content, file_folder, files, retmsg

    @staticmethod
    def __get_url_torrent_filename(req, url):
        """
        从下载请求中获取种子文件名
        """
        if not req:
            return ""
        disposition = req.headers.get('content-disposition') or ""
        file_name = re.findall(r"filename=\"?(.+)\"?", disposition)
        if file_name:
            file_name = unquote(str(file_name[0].encode('ISO-8859-1').decode()).split(";")[0].strip())
            if file_name.endswith('"'):
                file_name = file_name[:-1]
        elif url and url.endswith(".torrent"):
            file_name = unquote(url.split("/")[-1])
        else:
            file_name = str(datetime.datetime.now())
        return file_name

    @staticmethod
    def get_magnet_title(url):
        """
        从磁力链接中获取标题
        """
        if not url:
            return ""
        title = re.findall(r"dn=(.+)&?", url)
        return unquote(title[0]) if title else ""

    @staticmethod
    def get_intersection_episodes(target, source, title):
        """
        对两个季集字典进行判重，有相同项目的取集的交集
        """
        if not source or not title:
            return target
        if not source.get(title):
            return target
        if not target.get(title):
            target[title] = source.get(title)
            return target
        index = -1
        for target_info in target.get(title):
            index += 1
            source_info = None
            for info in source.get(title):
                if info.get("season") == target_info.get("season"):
                    source_info = info
                    break
            if not source_info:
                continue
            if not source_info.get("episodes"):
                continue
            if not target_info.get("episodes"):
                target_episodes = source_info.get("episodes")
                target[title][index]["episodes"] = target_episodes
                continue
            target_episodes = list(set(target_info.get("episodes")).intersection(set(source_info.get("episodes"))))
            target[title][index]["episodes"] = target_episodes
        return target

    @staticmethod
    def get_download_list(media_list, download_order):
        """
        对媒体信息进行排序、去重
        """
        if not media_list:
            return []

        # 排序函数，标题、站点、资源类型、做种数量
        def get_sort_str(x):
            season_len = str(len(x.get_season_list())).rjust(2, '0')
            episode_len = str(len(x.get_episode_list())).rjust(4, '0')
            # 排序：标题、资源类型、站点、做种、季集
            if download_order == "seeder":
                return "%s%s%s%s%s" % (str(x.title).ljust(100, ' '),
                                       str(x.res_order).rjust(3, '0'),
                                       str(x.seeders).rjust(10, '0'),
                                       str(x.site_order).rjust(3, '0'),
                                       "%s%s" % (season_len, episode_len))
            else:
                return "%s%s%s%s%s" % (str(x.title).ljust(100, ' '),
                                       str(x.res_order).rjust(3, '0'),
                                       str(x.site_order).rjust(3, '0'),
                                       str(x.seeders).rjust(10, '0'),
                                       "%s%s" % (season_len, episode_len))

        # 匹配的资源中排序分组选最好的一个下载
        # 按站点顺序、资源匹配顺序、做种人数下载数逆序排序
        media_list = sorted(media_list, key=lambda x: get_sort_str(x), reverse=True)
        # 控重
        can_download_list_item = []
        can_download_list = []
        # 排序后重新加入数组，按真实名称控重，即只取每个名称的第一个
        for t_item in media_list:
            # 控重的主链是名称、年份、季、集
            if t_item.type != MediaType.MOVIE:
                media_name = "%s%s" % (t_item.get_title_string(),
                                       t_item.get_season_episode_string())
            else:
                media_name = t_item.get_title_string()
            if media_name not in can_download_list:
                can_download_list.append(media_name)
                can_download_list_item.append(t_item)
        return can_download_list_item
