import time
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning
import os
import json
from urllib.parse import urlparse

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从配置文件读取 suno_url
def load_config():
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sunoplayer', 'config.json')
        if not os.path.exists(config_path):
            # 尝试在当前目录的父目录查找
            config_path = os.path.join(os.path.dirname(__file__), '..', 'sunoplayer', 'config.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('suno_url', 'https://suno-api-eta.vercel.app')
        else:
            logger.warning(f"配置文件不存在: {config_path}，使用默认URL")
            return 'https://suno-api-eta.vercel.app'
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}，使用默认URL")
        return 'https://suno-api-eta.vercel.app'

# 设置 base_url
base_url = load_config()
logger.info(f"使用 Suno API URL: {base_url}")

# 创建带有重试机制的会话
def create_session(max_retries=5):
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# 创建全局会话对象
session = create_session()

# 禁用不安全警告（仅当verify=False时使用）
# requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def custom_generate_audio(payload):
    url = f"{base_url}/api/custom_generate"
    try:
        response = session.post(
            url, 
            json=payload, 
            headers={'Content-Type': 'application/json'},
            timeout=30  # 添加超时设置
        )
        response.raise_for_status()  # 如果状态码不是200系列，将引发异常
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def extend_audio(payload):
    url = f"{base_url}/api/extend_audio"
    try:
        response = session.post(
            url, 
            json=payload, 
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def generate_audio_by_prompt(payload):
    url = f"{base_url}/api/generate"
    try:
        response = session.post(
            url, 
            json=payload, 
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def get_audio_information(audio_ids):
    url = f"{base_url}/api/get?ids={audio_ids}"
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def get_quota_information():
    url = f"{base_url}/api/get_limit"
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def get_clip(clip_id):
    url = f"{base_url}/api/clip?id={clip_id}"
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def generate_whole_song(clip_id):
    payload = {"clip_id": clip_id}
    url = f"{base_url}/api/concat"
    try:
        response = session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {"error": str(e)}

def check_api_health():
    """检查API健康状态"""
    try:
        response = session.get(f"{base_url}", timeout=10)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def get_aligned_lyrics(audio_id):
    """
    获取音频的对齐歌词（每个单词的时间戳）
    
    参数:
        audio_id (str): 音频ID
        
    返回:
        dict: 包含歌词和时间戳的数据
    """
    url = f"{base_url}/api/get_aligned_lyrics?song_id={audio_id}"
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"获取歌词失败: {e}")
        return {"error": str(e)}

def save_lyrics_to_txt(lyrics_data, output_path):
    """
    将歌词数据保存为TXT文件，不包含时间戳
    
    参数:
        lyrics_data (dict/list): 歌词数据
        output_path (str): 保存文件的路径
        
    返回:
        str: 保存的文件路径
    """
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 检查是否有错误
        if isinstance(lyrics_data, dict) and "error" in lyrics_data:
            logger.error(f"歌词数据包含错误: {lyrics_data['error']}")
            return None
        
        # 提取歌词文本
        processed_lyrics = ""
        current_line = ""
        
        # 处理列表格式的歌词数据（英文歌词通常是这种格式）
        if isinstance(lyrics_data, list):
            for item in lyrics_data:
                if "word" in item:
                    word = item["word"]
                    
                    # 检查是否包含章节标记 [Verse], [Chorus] 等
                    if word.startswith("[") and "]" in word:
                        section_end = word.find("]") + 1
                        section = word[:section_end]
                        
                        # 如果当前行不为空，先添加当前行
                        if current_line:
                            processed_lyrics += current_line.strip() + "\n"
                            current_line = ""
                        
                        # 添加章节标记为单独的一行
                        processed_lyrics += section + "\n"
                        
                        # 处理章节标记后的剩余部分
                        remaining = word[section_end:].strip()
                        if remaining:
                            if "\n" in remaining:
                                parts = remaining.split("\n")
                                for i, part in enumerate(parts):
                                    if part:
                                        current_line += part + " "
                                    if i < len(parts) - 1:  # 不是最后一部分
                                        processed_lyrics += current_line.strip() + "\n"
                                        current_line = ""
                            else:
                                current_line += remaining + " "
                    else:
                        # 检查是否包含换行符
                        if "\n" in word:
                            parts = word.split("\n")
                            for i, part in enumerate(parts):
                                if part:
                                    current_line += part + " "
                                if i < len(parts) - 1:  # 不是最后一部分
                                    processed_lyrics += current_line.strip() + "\n"
                                    current_line = ""
                        else:
                            current_line += word + " "
            
            # 添加最后一行
            if current_line:
                processed_lyrics += current_line.strip() + "\n"
        
        # 处理字典格式的歌词数据
        elif isinstance(lyrics_data, dict):
            # 现有的字典处理逻辑保持不变
            if "words" in lyrics_data:
                # 如果是单词级别的数据
                for word_data in lyrics_data["words"]:
                    if "word" in word_data:
                        word = word_data["word"].strip()
                        if "\n" in word:
                            parts = word.split("\n")
                            for i, part in enumerate(parts):
                                if part:
                                    current_line += part + " "
                                if i < len(parts) - 1:  # 不是最后一部分
                                    processed_lyrics += current_line.strip() + "\n"
                                    current_line = ""
                        else:
                            current_line += word + " "
                
                # 添加最后一行
                if current_line:
                    processed_lyrics += current_line.strip() + "\n"
            elif "lines" in lyrics_data:
                # 如果是行级别的数据
                for line_data in lyrics_data["lines"]:
                    if "text" in line_data:
                        text = line_data["text"].strip()
                        processed_lyrics += text + "\n"
            else:
                # 如果只有纯文本歌词
                processed_lyrics = lyrics_data.get("lyrics", "")
        else:
            logger.warning("未知的歌词数据格式")
            return None
        
        # 保存到文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(processed_lyrics)
        
        logger.info(f"歌词已保存至: {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"保存歌词时出错: {e}")
        return None
    
def download_audio(audio_url, output_path=None, file_format='mp3'):
    """
    从给定的URL下载音频并保存为MP3或WAV格式
    
    参数:
        audio_url (str): 音频文件的URL
        output_path (str, optional): 保存文件的路径。如果为None，将使用URL中的ID作为文件名
        file_format (str, optional): 保存的文件格式，'mp3'或'wav'。默认为'mp3'
        
    返回:
        str: 保存的文件路径
    """
    if file_format not in ['mp3', 'wav']:
        logger.warning(f"不支持的文件格式: {file_format}，将使用默认格式mp3")
        file_format = 'mp3'
    
    try:
        # 从URL中提取ID作为文件名
        if not output_path:
            parsed_url = urlparse(audio_url)
            query_params = parsed_url.query.split('=')
            if len(query_params) > 1:
                file_id = query_params[1]
                output_path = f"{file_id}.{file_format}"
            else:
                # 如果无法从URL提取ID，使用时间戳作为文件名
                output_path = f"suno_audio_{int(time.time())}.{file_format}"
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        logger.info(f"正在下载音频: {audio_url}")
        response = session.get(audio_url, stream=True, timeout=60)
        response.raise_for_status()
        
        # 检查内容类型和长度
        content_type = response.headers.get('Content-Type', '')
        content_length = response.headers.get('Content-Length', '0')
        logger.info(f"响应内容类型: {content_type}, 内容长度: {content_length}")
        
        # 保存文件
        total_size = 0
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # 过滤掉保持连接alive的空块
                    f.write(chunk)
                    total_size += len(chunk)
        
        # 验证文件大小
        file_size = os.path.getsize(output_path)
        logger.info(f"音频已保存至: {output_path}, 文件大小: {file_size} 字节, 下载大小: {total_size} 字节")
        
        # 如果文件太小，可能是下载失败
        if file_size < 1024:  # 小于1KB
            logger.warning(f"警告: 下载的文件太小 ({file_size} 字节), 可能下载不完整")
            
        return output_path
    
    except requests.exceptions.RequestException as e:
        logger.error(f"下载音频失败: {e}")
        return None
    except Exception as e:
        logger.error(f"保存音频时出错: {e}")
        return None
    
def download_audio_with_lyrics(audio_id, audio_url, output_dir="downloads", file_format='mp3'):
    """
    下载音频并同时获取和保存歌词
    
    参数:
        audio_id (str): 音频ID
        audio_url (str): 音频URL
        output_dir (str): 保存目录
        file_format (str): 音频格式
        
    返回:
        tuple: (音频文件路径, 歌词文件路径)
    """
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 下载音频
    audio_path = download_audio(
        audio_url,
        output_path=f"{output_dir}/{audio_id}.{file_format}",
        file_format=file_format
    )
    
    # 获取歌词
    lyrics_data = get_aligned_lyrics(audio_id)
    lyrics_path = None
    
    if "error" not in lyrics_data:
        # 保存歌词
        lyrics_path = save_lyrics_to_txt(
            lyrics_data,
            output_path=f"{output_dir}/{audio_id}_lyrics.txt"
        )
    else:
        logger.warning(f"无法获取歌词: {lyrics_data.get('error', '未知错误')}")
    
    return audio_path, lyrics_path

if __name__ == '__main__':
    # 首先检查API可用性
    if not check_api_health():
        logger.warning(f"警告: API端点 {base_url} 似乎不可用。继续尝试...")
    
    try:
        logger.info("正在生成音频...")
        data = generate_audio_by_prompt({
            "prompt": "宝可梦之歌",
            "make_instrumental": False,
            "model": "chirp-v4-0",
            "wait_audio": False
        })
        
        # 检查返回数据中是否有错误
        if "error" in data:
            logger.error(f"生成音频时出错: {data['error']}")
            exit(1)
            
        ids = f"{data[0]['id']},{data[1]['id']}"
        logger.info(f"音频ID: {ids}")

        for attempt in range(60):
            logger.info(f"正在检查音频状态 (尝试 {attempt+1}/60)...")
            try:
                data = get_audio_information(ids)
                
                # 检查返回数据中是否有错误
                if "error" in data:
                    logger.error(f"获取音频信息时出错: {data['error']}")
                    time.sleep(5)
                    continue
                
                if data[0]["status"] == 'streaming':
                    logger.info(f"音频已准备就绪!")
                    logger.info(f"{data[0]['id']} ==> {data[0]['audio_url']}")
                    logger.info(f"{data[1]['id']} ==> {data[1]['audio_url']}")
                    
                    # 创建下载目录
                    download_dir = "downloads"
                    
                    # 下载音频和歌词
                    for item in data:
                        audio_id = item['id']
                        audio_url = item['audio_url']
                        
                        # 使用新函数下载音频和歌词
                        audio_path, lyrics_path = download_audio_with_lyrics(
                            audio_id,
                            audio_url,
                            output_dir=download_dir,
                            file_format='mp3'
                        )
                        
                        if audio_path:
                            logger.info(f"音频已下载: {audio_path}")
                        if lyrics_path:
                            logger.info(f"歌词已下载: {lyrics_path}")
                    
                    break
            except Exception as e:
                logger.error(f"处理响应时出错: {e}")
            
            # 休眠5秒
            logger.info("等待5秒...")
            time.sleep(5)
        else:
            logger.warning("达到最大尝试次数，音频可能尚未准备好")
    
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
