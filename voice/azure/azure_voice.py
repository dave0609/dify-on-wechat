"""
azure voice service
"""
import json
import os
import time

import azure.cognitiveservices.speech as speechsdk
from langid import classify

from bridge.reply import Reply, ReplyType
from common.log import logger
from common.tmp_dir import TmpDir
from config import conf
from voice.voice import Voice

"""
Azure voice
主目录设置文件中需填写azure_voice_api_key和azure_voice_region

查看可用的 voice： https://speech.microsoft.com/portal/voicegallery

"""


class AzureVoice(Voice):
    def __init__(self):
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            config = None
            if not os.path.exists(config_path):  # 如果没有配置文件，创建本地配置文件
                config = {
                    "speech_synthesis_voice_name": "zh-CN-XiaoshuangNeural",  # 识别不出时的默认语音
                    "auto_detect": True,  # 是否自动检测语言
                    "speech_synthesis_zh": "zh-CN-XiaoshuangNeural",
                    "speech_synthesis_en": "en-US-JacobNeural",
                    "speech_synthesis_ja": "ja-JP-AoiNeural",
                    "speech_synthesis_ko": "ko-KR-SoonBokNeural",
                    "speech_synthesis_de": "de-DE-LouisaNeural",
                    "speech_synthesis_fr": "fr-FR-BrigitteNeural",
                    "speech_synthesis_es": "es-ES-LaiaNeural",
                    "speech_recognition_language": "zh-CN",
                }
                with open(config_path, "w") as fw:
                    json.dump(config, fw, indent=4)
            else:
                with open(config_path, "r") as fr:
                    config = json.load(fr)
            self.config = config
            self.api_key = conf().get("azure_voice_api_key")
            self.api_region = conf().get("azure_voice_region")
            
            # 验证API密钥和区域是否已配置
            if not self.api_key or not self.api_region:
                logger.error("[Azure] Missing API key or region in configuration")
                raise ValueError("Azure Speech Service requires both api_key and region to be configured")
            
            # 创建语音配置
            self.speech_config = speechsdk.SpeechConfig(subscription=self.api_key, region=self.api_region)
            
            # 尝试使用REST API而不是WebSocket
            self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_TranslationUseWebsockets, "false")
            
            # 设置连接超时时间（毫秒）
            self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_ConnectTimeout, "10000")
            
            # 配置语音合成和识别语言
            self.speech_config.speech_synthesis_voice_name = self.config["speech_synthesis_voice_name"]
            self.speech_config.speech_recognition_language = self.config["speech_recognition_language"]
            
            # 记录初始化信息
            logger.info(f"[Azure] Initialized with region: {self.api_region}, voice: {self.speech_config.speech_synthesis_voice_name}")
        except Exception as e:
            logger.warn("AzureVoice init failed: %s, ignore " % e)

    def voiceToText(self, voice_file):
        try:
            audio_config = speechsdk.AudioConfig(filename=voice_file)
            speech_recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config, audio_config=audio_config)
            
            logger.info(f"[Azure] Starting voice recognition for file: {voice_file}")
            result = speech_recognizer.recognize_once()
            
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                logger.info("[Azure] voiceToText voice file name={} text={}".format(voice_file, result.text))
                reply = Reply(ReplyType.TEXT, result.text)
            else:
                cancel_details = result.cancellation_details
                logger.error("[Azure] voiceToText error, result={}, errordetails={}".format(result, cancel_details))
                reply = Reply(ReplyType.ERROR, "抱歉，语音识别失败")
        except Exception as e:
            logger.error(f"[Azure] voiceToText exception: {str(e)}")
            reply = Reply(ReplyType.ERROR, f"语音识别异常: {str(e)}")
        return reply
    
    def _generate_ssml(self, text, rate="1.0"):
        """生成SSML标记语言
        Args:
            text (str): 要转换的文本
            rate (str): 语速 (e.g., "0.8", "1.0", "1.2")
        """
        voice_name = self.speech_config.speech_synthesis_voice_name
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            f'<voice name="{voice_name}">'
            f'<prosody rate="{rate}">{text}</prosody>'
            f'</voice>'
            f'</speak>'
        )
        return ssml

    def textToVoiceWithSSML(self, text, use_auto_detect=None, rate="1.0"):
        """使用SSML将文本转换为语音，支持设置语速
        Args:
            text (str): 要转换的文本
            use_auto_detect (bool, optional): 是否自动检测语言
            rate (str, optional): 语速，默认"1.0"，范围一般在0.5到2.0之间
        Returns:
            Reply: 语音回复对象
        """
        try:
            # If use_auto_detect is provided, use it; otherwise use the config value
            should_auto_detect = self.config.get("auto_detect") if use_auto_detect is None else use_auto_detect
            
            if should_auto_detect:
                lang = classify(text)[0]
                key = "speech_synthesis_" + lang
                if key in self.config:
                    logger.info("[Azure] textToVoice auto detect language={}, voice={}".format(lang, self.config[key]))
                    self.speech_config.speech_synthesis_voice_name = self.config[key]
                else:
                    self.speech_config.speech_synthesis_voice_name = self.config["speech_synthesis_voice_name"]

            fileName = TmpDir().path() + "reply-" + str(int(time.time())) + "-" + str(hash(text) & 0x7FFFFFFF) + ".wav"
            audio_config = speechsdk.AudioConfig(filename=fileName)
            
            # 记录详细的合成信息
            logger.info(f"[Azure] Attempting TTS with region: {self.api_region}, voice: {self.speech_config.speech_synthesis_voice_name}, file: {fileName}")
            
            speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config, audio_config=audio_config)
            
            # 使用SSML来控制语速
            ssml = self._generate_ssml(text, rate)
            result = speech_synthesizer.speak_ssml(ssml)
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info("[Azure] textToVoice text={} voice file name={}".format(text, fileName))
                reply = Reply(ReplyType.FILE, fileName)
            else:
                cancel_details = result.cancellation_details
                error_msg = f"[Azure] textToVoice error, result={result}, errordetails={cancel_details.error_details if cancel_details else 'Unknown'}"
                logger.error(error_msg)
                
                # 尝试使用备用方法
                logger.info("[Azure] Trying alternative synthesis method...")
                result = speech_synthesizer.speak_text(text)
                
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    logger.info("[Azure] Alternative method succeeded, text={} voice file name={}".format(text, fileName))
                    reply = Reply(ReplyType.FILE, fileName)
                else:
                    cancel_details = result.cancellation_details
                    logger.error("[Azure] Alternative method failed, result={}, errordetails={}".format(
                        result, cancel_details.error_details if cancel_details else 'Unknown'))
                    reply = Reply(ReplyType.ERROR, "抱歉，语音合成失败")
        except Exception as e:
            logger.error(f"[Azure] textToVoiceWithSSML exception: {str(e)}")
            reply = Reply(ReplyType.ERROR, f"语音合成异常: {str(e)}")
        return reply

    def textToVoice(self, text, use_auto_detect=None):
        try:
            # If use_auto_detect is provided, use it; otherwise use the config value
            should_auto_detect = self.config.get("auto_detect") if use_auto_detect is None else use_auto_detect
            
            if should_auto_detect:
                lang = classify(text)[0]
                key = "speech_synthesis_" + lang
                if key in self.config:
                    logger.info("[Azure] textToVoice auto detect language={}, voice={}".format(lang, self.config[key]))
                    self.speech_config.speech_synthesis_voice_name = self.config[key]
                else:
                    self.speech_config.speech_synthesis_voice_name = self.config["speech_synthesis_voice_name"]
            # else: keep the current speech_synthesis_voice_name setting
            
            # Avoid the same filename under multithreading
            fileName = TmpDir().path() + "reply-" + str(int(time.time())) + "-" + str(hash(text) & 0x7FFFFFFF) + ".wav"
            audio_config = speechsdk.AudioConfig(filename=fileName)
            
            # 记录详细的合成信息
            logger.info(f"[Azure] Attempting TTS with region: {self.api_region}, voice: {self.speech_config.speech_synthesis_voice_name}, file: {fileName}")
            
            # 尝试使用REST API
            speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config, audio_config=audio_config)
            
            # 首先尝试使用标准方法
            result = speech_synthesizer.speak_text(text)
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info("[Azure] textToVoice text={} voice file name={}".format(text, fileName))
                reply = Reply(ReplyType.FILE, fileName)
            else:
                cancel_details = result.cancellation_details
                error_msg = f"[Azure] textToVoice error, result={result}, errordetails={cancel_details.error_details if cancel_details else 'Unknown'}"
                logger.error(error_msg)
                
                # 如果失败，尝试使用备用区域
                backup_region = "eastus" if self.api_region != "eastus" else "westus"
                logger.info(f"[Azure] Trying backup region: {backup_region}")
                
                backup_config = speechsdk.SpeechConfig(subscription=self.api_key, region=backup_region)
                backup_config.speech_synthesis_voice_name = self.speech_config.speech_synthesis_voice_name
                backup_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_TranslationUseWebsockets, "false")
                
                backup_synthesizer = speechsdk.SpeechSynthesizer(speech_config=backup_config, audio_config=audio_config)
                backup_result = backup_synthesizer.speak_text(text)
                
                if backup_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    logger.info(f"[Azure] Backup region {backup_region} succeeded, text={text} voice file name={fileName}")
                    reply = Reply(ReplyType.FILE, fileName)
                else:
                    backup_details = backup_result.cancellation_details
                    logger.error(f"[Azure] Backup region failed, result={backup_result}, errordetails={backup_details.error_details if backup_details else 'Unknown'}")
                    reply = Reply(ReplyType.ERROR, "抱歉，语音合成失败")
        except Exception as e:
            logger.error(f"[Azure] textToVoice exception: {str(e)}")
            reply = Reply(ReplyType.ERROR, f"语音合成异常: {str(e)}")
        return reply