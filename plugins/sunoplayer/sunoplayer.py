import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from common.tmp_dir import TmpDir

import os
import uuid
from glob import glob
from .suno import (generate_audio_by_prompt, get_audio_information, 
                  download_audio_with_lyrics, download_audio, get_quota_information)
import time

@plugins.register(
    name="sunoplayer",
    desire_priority=2,
    desc="A plugin to call suno API",
    version="0.1.0",
    author="davexxx",
)

class sunoplayer(Plugin):
    def __init__(self):
        super().__init__()
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                # 使用父类的方法来加载配置
                self.config = super().load_config()

                if not self.config:
                    raise Exception("config.json not found")
            
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            # 从配置中提取所需的设置
            self.show_lyc = self.config.get("show_lyc",False)
            self.suno_prefix = self.config.get("suno_prefix", "suno")
            self.instrumental_prefix = self.config.get("instrumental_prefix", "instrumental")

            # 初始化成功日志
            logger.info("[sunoplayer] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"sunoplayer init failed: {e}")
    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.SHARING,ContextType.FILE,ContextType.IMAGE]:
            return
        content = context.content

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.suno_prefix):
                # Call new function to handle search operation
                pattern = self.suno_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了suno的指令
                    logger.info("calling suno service")
                    prompt = content[len(self.suno_prefix):].strip()
                    logger.info(f"suno prompt = : {prompt}")
                    try:
                        # Remove custom parameter, always set to False
                        instrumental = False
                        self.call_suno_service(prompt, instrumental, e_context)
                    except Exception as e:
                        logger.error("create song error: {}".format(e))
                        rt = ReplyType.TEXT
                        rc = "服务暂不可用,可能是某些词汇没有通过安全审查"
                        reply = Reply(rt, rc)
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                else:
                    tip = f"💡欢迎使用写歌服务，指令格式为:\n\n{self.suno_prefix}+ 空格 + 对歌曲主题的描述(控制在30个字之内)\n例如:\n{self.suno_prefix} 一首浪漫的情歌\n或者:\n{self.suno_prefix} a blue cyber dream song"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

            if content.startswith(self.instrumental_prefix):
                # Call new function to handle search operation
                pattern = self.instrumental_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match: ##   匹配上了instrumental的指令
                    logger.info("calling instrumental suno service")
                    prompt = content[len(self.instrumental_prefix):].strip()
                    logger.info(f"instrumental suno prompt =  {prompt}")
                    try:
                        # Remove custom parameter, always set to False
                        instrumental = True
                        self.call_suno_service(prompt, instrumental, e_context)
                    except Exception as e:
                        logger.error("create song error: {}".format(e))
                        rt = ReplyType.TEXT
                        rc = "服务暂不可用"
                        reply = Reply(rt, rc)
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                else:
                    tip = f"💡欢迎使用纯乐曲创作服务，指令格式为:\n\n{self.instrumental_prefix}+ 空格 + 对歌曲主题的描述(控制在30个字之内)\n例如:\n{self.instrumental_prefix} 一首浪漫的情歌\n或者:\n{self.instrumental_prefix} a blue cyber dream song"
                    reply = Reply(type=ReplyType.TEXT, content= tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS


    def call_suno_service(self, prompt, instrumental, e_context):
        output_dir = self.generate_unique_output_directory(TmpDir().path())
        logger.info(f"output dir = {output_dir}")
        song_detail = prompt

        # Check quota instead of using SongsGen
        quota_info = get_quota_information()
        if "error" in quota_info:
            logger.error(f"Error checking quota: {quota_info['error']}")
            rt = ReplyType.TEXT
            rc = "服务暂不可用，无法检查额度"
            reply = Reply(rt, rc)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return
        
        quota_left = quota_info.get("credits_left", 0)
        logger.info(f"credit left = {quota_left}")
        if quota_left < 1:
            logger.info("No enough credit left.")
            rt = ReplyType.TEXT
            rc = "账户额度不够，请联系管理员"
            reply = Reply(rt, rc)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        tip = '您的作曲之旅已经启航，让我们的音乐小精灵带上您的歌词飞向创意的宇宙！请耐心等待2~5分钟，您的个人音乐风暴就会随着节拍轻轻降落。准备好一起摇摆吧！🚀'
        self.send_reply(tip, e_context)

        try:
            # Remove custom mode, only use generate_audio_by_prompt
            logger.info("theme/instrumental mode")
            # For theme or instrumental mode
            data = generate_audio_by_prompt({
                "prompt": song_detail,
                "make_instrumental": instrumental,
                "model": "chirp-v4-0",
                "wait_audio": False
            })
            
            # Check for errors in response
            if "error" in data:
                logger.error(f"Error generating audio: {data['error']}")
                rt = ReplyType.TEXT
                rc = "生成失败，服务不可用"
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            # Get audio IDs from response
            audio_ids = ",".join([item['id'] for item in data])
            logger.info(f"Audio IDs: {audio_ids}")
            
            # Wait for audio to be ready
            audio_data = None
            for attempt in range(60):
                logger.info(f"Checking audio status (attempt {attempt+1}/60)...")
                try:
                    audio_data = get_audio_information(audio_ids)
                    
                    if "error" in audio_data:
                        logger.error(f"Error getting audio info: {audio_data['error']}")
                        time.sleep(5)
                        continue
                    
                    # Check if all audio clips are ready
                    all_ready = all(item.get("status") == "streaming" for item in audio_data)
                    if all_ready:
                        logger.info("All audio clips are ready!")
                        break
                except Exception as e:
                    logger.error(f"Error processing response: {e}")
                
                logger.info("Waiting 5 seconds...")
                time.sleep(5)
            
            if not audio_data or not all(item.get("status") == "streaming" for item in audio_data):
                logger.warning("Maximum attempts reached, audio may not be ready")
                rt = ReplyType.TEXT
                rc = "生成超时，请稍后再试"
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            
            # Process each audio clip
            file_counter = 0
            total_files = len(audio_data)
            final_reply = None
            
            for item in audio_data:
                file_counter += 1
                audio_id = item['id']
                audio_url = item['audio_url']
                
                # Use download_audio_with_lyrics instead of separate functions
                if not instrumental and self.show_lyc:
                    audio_path, lyrics_path = download_audio_with_lyrics(
                        audio_id,
                        audio_url,
                        output_dir=output_dir,
                        file_format='mp3'
                    )
                    
                    # Send lyrics if available
                    if lyrics_path and os.path.exists(lyrics_path):
                        msg = self.print_file_contents(lyrics_path)
                        self.send_reply(msg, e_context)
                else:
                    # Just download audio if no lyrics needed
                    audio_path = download_audio(
                        audio_url,
                        output_path=os.path.join(output_dir, f"{audio_id}.mp3"),
                        file_format='mp3'
                    )
                
                if not audio_path or not self.is_valid_file(audio_path):
                    logger.error(f"Failed to download or invalid audio file: {audio_id}")
                    continue
                
                # Rename and send the audio file
                newfilepath = self.rename_file(audio_path, prompt, file_counter)
                rt = ReplyType.FILE
                rc = newfilepath
                self.send_reply(rc, e_context, rt)
                
                # Set final reply for the last file
                if file_counter == total_files:
                    final_reply = Reply(rt, rc)
            
            # If no files were processed successfully
            if file_counter == 0:
                logger.info("No media files were processed successfully.")
                final_reply = Reply(ReplyType.TEXT, "生成失败，服务不可用")
            
            # Set final action
            if final_reply:
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            logger.error(f"Error in call_suno_service: {e}")
            rt = ReplyType.TEXT
            rc = "服务暂不可用，发生错误"
            reply = Reply(rt, rc)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS


    def is_valid_file(self, file_path, min_size=100*1024):  # 100KB
        """Check if the file exists and is greater than a given minimum size in bytes."""
        return os.path.exists(file_path) and os.path.getsize(file_path) > min_size

    def find_lrc_files(self, directory):
        """Find the first .lrc file in a directory."""
        lrc_files = glob(os.path.join(directory, '*.lrc'))
        return lrc_files[0] if lrc_files else None

    def generate_unique_output_directory(self, base_dir):
        """Generate a unique output directory using a UUID."""
        unique_dir = os.path.join(base_dir, str(uuid.uuid4()))
        os.makedirs(unique_dir, exist_ok=True)
        return unique_dir

    def print_file_contents(self, file_path):
        """Read and print the contents of the file."""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
        
    def send_reply(self, reply, e_context: EventContext, reply_type=ReplyType.TEXT):
        if isinstance(reply, Reply):
            if not reply.type and reply_type:
                reply.type = reply_type
        else:
            reply = Reply(reply_type, reply)
        channel = e_context['channel']
        context = e_context['context']
        # reply的包装步骤
        rd = channel._decorate_reply(context, reply)
        # reply的发送步骤
        return channel._send_reply(context, rd)
    
    def rename_file(self, filepath, prompt, file_counter):
        # 提取目录路径和扩展名
        dir_path, filename = os.path.split(filepath)
        file_ext = os.path.splitext(filename)[1]

        # 移除prompt中的标点符号和空格
        cleaned_content = re.sub(r'[^\w]', '', prompt)
        # 截取prompt的前10个字符
        content_prefix = cleaned_content[:10]
                
        # 组装新的文件名
        new_filename = f"{content_prefix}-{file_counter}"

        # 拼接回完整的新文件路径
        new_filepath = os.path.join(dir_path, new_filename + file_ext)

        # 重命名原文件
        try:
            os.rename(filepath, new_filepath)
        except OSError as e:
            logger.error(f"Error: {e.strerror}")
            return filepath

        return new_filepath