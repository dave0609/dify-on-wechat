import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from common.tmp_dir import TmpDir
from common.expired_dict import ExpiredDict
import asyncio  # 新增导入
import fal_client  # 新增导入
import requests 
import os
import os
import uuid
from glob import glob


@plugins.register(
    name="falclient",
    desire_priority=2,
    desc="A plugin to call falclient API",
    version="0.0.1",
    author="davexxx",
)

class falclient(Plugin):
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

            self.fal_kling_text_prefix = self.config.get("fal_kling_text_prefix", "文生视频")
            self.fal_kling_text_model = self.config.get("fal_kling_text_model", "kling-video/v1.6/standard/text-to-video")
            self.fal_kling_img_prefix = self.config.get("fal_kling_img_prefix", "图生视频")
            self.fal_kling_img_model = self.config.get("fal_kling_img_model", "kling-video/v1.6/standard/image-to-video")
            self.fal_api_key = self.config.get("fal_api_key", "")
            self.params_cache = ExpiredDict(500)

            # 初始化成功日志
            logger.info("[falclient] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"falclient init failed: {e}")

    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.SHARING, ContextType.FILE, ContextType.IMAGE]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        user_id = msg.from_user_id
        content = context.content

        # 将用户信息存储在params_cache中
        if user_id not in self.params_cache:
            self.params_cache[user_id] = {}
            self.params_cache[user_id]['kling_img_quota'] = 0
            self.params_cache[user_id]['fal_kling_img_prefix'] = None
            logger.debug('Added new user to params_cache. user id = ' + user_id)

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.fal_kling_img_prefix):
                pattern = self.fal_kling_img_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match:  # 匹配上了kling的指令
                    img_prompt = content[len(self.fal_kling_img_prefix):].strip()
                    self.params_cache[user_id]['kling_img_prompt'] = img_prompt
                    self.params_cache[user_id]['kling_img_quota'] = 1
                    tip = f"💡已经开启kling图片生成视频服务，请再发送一张图片进行处理，当前的提示词为:\n{img_prompt}"
                else:
                    tip = f"💡欢迎使用kling图片生成视频服务，指令格式为:\n\n{self.fal_kling_img_prefix} + 对视频的描述\n例如：{self.fal_kling_img_prefix} make the picture alive."

                reply = Reply(type=ReplyType.TEXT, content=tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

            elif content.startswith(self.fal_kling_text_prefix):
                pattern = self.fal_kling_text_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                if match:  # 匹配上了kling的指令
                    text_prompt = content[len(self.fal_kling_text_prefix):].strip()
                    self.call_fal_service(text_prompt, e_context)
                else:
                    tip = f"💡欢迎使用kling文字生成视频服务，指令格式为:\n\n{self.fal_kling_text_prefix} + 对视频的描述\n例如：{self.fal_kling_text_prefix} a girl is walking in the street."
                    reply = Reply(type=ReplyType.TEXT, content=tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

        elif context.type == ContextType.IMAGE:
            if self.params_cache[user_id]['kling_img_quota'] < 1:
                # 进行下一步的操作                
                logger.debug("on_handle_context: 当前用户生成视频配额不够，不进行识别")
                return

            logger.info("on_handle_context: 开始处理图片")
            context.get("msg").prepare()
            image_path = context.content
            logger.info(f"on_handle_context: 获取到图片路径 {image_path}")

            if self.params_cache[user_id]['kling_img_quota'] > 0:
                self.params_cache[user_id]['kling_img_quota'] = 0
                self.call_kling_service(image_path, user_id, e_context)

            # 删除文件
            os.remove(image_path)
            logger.info(f"文件 {image_path} 已删除")
    
    def generate_unique_output_directory(self, base_dir):
        """Generate a unique output directory using a UUID."""
        unique_dir = os.path.join(base_dir, str(uuid.uuid4()))
        os.makedirs(unique_dir, exist_ok=True)
        return unique_dir
    
    def is_valid_file(self, file_path, min_size=100*1024):  # 100KB
        """Check if the file exists and is greater than a given minimum size in bytes."""
        return os.path.exists(file_path) and os.path.getsize(file_path) > min_size


    def call_kling_service(self, image_path, user_id, e_context):
        try:
            # 设置 API 密钥
            api_key = self.fal_api_key
            
            # 获取用户的提示词
            prompt = self.params_cache[user_id].get('kling_img_prompt', '')
            
            tip = '您的视频请求已经进入队列，大概需要5-6分钟，请耐心等候。请注意：由于协议限制，生成视频将会以文件形式发送。'
            self.send_reply(tip, e_context)
            
            # 创建 fal_client 实例
            client = fal_client.SyncClient(key=api_key)
            
            # 上传图片获取URL
            logger.info(f"开始上传图片: {image_path}")
            image_url = client.upload_file(image_path)
            logger.info(f"图片上传成功，URL: {image_url}")
            
            # 使用图片URL生成视频
            logger.info(f"开始使用图片URL生成视频，提示词: {prompt}")
            
            # 定义回调函数来处理队列更新
            def on_queue_update(update):
                if isinstance(update, fal_client.InProgress):
                    # 只记录第一条日志或状态变化
                    if update.logs and len(update.logs) > 0:
                        latest_log = update.logs[-1]
                        logger.info(f"处理进度: {latest_log['message']}")
                elif isinstance(update, fal_client.Queued):
                    # 只在队列位置变化时记录
                    static_position = getattr(on_queue_update, 'last_position', None)
                    if static_position != update.position:
                        logger.info(f"请求已排队，位置: {update.position}")
                        on_queue_update.last_position = update.position
            
            # 使用subscribe方法提交请求并等待结果
            result = client.subscribe(
                f"fal-ai/{self.fal_kling_img_model}",
                arguments={
                    "prompt": prompt,
                    "image_url": image_url
                },
                with_logs=False,
                on_queue_update=on_queue_update
            )
            
            logger.info(f"视频生成响应: {json.dumps(result, ensure_ascii=False)}")
            
            # 从结果中提取视频URL
            video_url = result.get("video", {}).get("url")
            
            if video_url:
                output_dir = self.generate_unique_output_directory(TmpDir().path())
                
                # 构建视频文件路径
                video_path = os.path.join(output_dir, f"kling_{uuid.uuid4()}.mp4")
                
                # 下载视频
                video_response = requests.get(video_url)
                with open(video_path, 'wb') as f:
                    f.write(video_response.content)
                
                self.send_reply(video_path, e_context, ReplyType.VIDEO)
                
                # 发送完成提示
                rt = ReplyType.TEXT
                rc = "可灵视频生成完毕。"
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc = "视频生成失败，请稍后重试"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error(f"[fal client] 未能从响应中提取视频URL: {result}")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            rc = f"服务暂不可用: {str(e)}"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error(f"[fal client] 服务异常: {e}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS


    def call_fal_service(self, prompt: str, e_context: EventContext):
        try:
            # 设置 API 密钥
            api_key = self.fal_api_key
            
            tip = '您的视频请求已经进入队列，大概需要5-6分钟，请耐心等候。请注意：由于协议限制，生成视频将会以文件形式发送。'
            self.send_reply(tip, e_context)

            # 使用 REST API 发送请求
            url = f"https://fal.run/fal-ai/{self.fal_kling_text_model}"
            headers = {
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "prompt": prompt
            }

            # 发送同步请求
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            
            if 'video' in result:
                output_dir = self.generate_unique_output_directory(TmpDir().path())

                video_url = result['video']['url']                    
                # 构建视频文件路径
                video_path = os.path.join(output_dir, f"kling_{uuid.uuid4()}.mp4")
                
                # 下载视频
                video_response = requests.get(video_url)
                with open(video_path, 'wb') as f:
                    f.write(video_response.content)
                
                self.send_reply(video_path, e_context, ReplyType.VIDEO)
                
                # 发送完成提示
                rt = ReplyType.TEXT
                rc = "可灵视频生成完毕。"
                reply = Reply(rt, rc)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                rc="视频生成失败，请稍后重试"
                rt = ReplyType.TEXT
                reply = Reply(rt, rc)
                logger.error("[fal client ] service exception")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            rc= "服务暂不可用"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[fal client ] service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
        
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
    
    def rename_file(self, filepath, prompt):
        # 提取目录路径和扩展名
        dir_path, filename = os.path.split(filepath)
        file_ext = os.path.splitext(filename)[1]

        # 移除prompt中的标点符号和空格
        cleaned_content = re.sub(r'[^\w]', '', prompt)
        # 截取prompt的前10个字符
        content_prefix = cleaned_content[:10]
                
        # 组装新的文件名
        new_filename = f"{content_prefix}"

        # 拼接回完整的新文件路径
        new_filepath = os.path.join(dir_path, new_filename + file_ext)

        # 重命名原文件
        try:
            os.rename(filepath, new_filepath)
        except OSError as e:
            logger.error(f"Error: {e.strerror}")
            return filepath

        return new_filepath