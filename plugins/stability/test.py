from google import genai
from google.genai import types
from PIL import Image
from IPython.display import display, Markdown, Image as IPythonImage
import os
import re
import json
import base64
import PIL
import traceback

# 从config.json读取API密钥
def load_api_key():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('google_key')
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return None

# 获取API密钥
api_key = load_api_key()
if not api_key:
    print("警告: 未能从config.json读取google_key，请确保配置文件存在且包含有效的密钥")
    exit(1)

client = genai.Client(api_key=api_key)

def display_response(response):
    print("Response object:", response)
    print("Response type:", type(response))
    
    # 检查响应是否有候选项
    if not hasattr(response, 'candidates') or not response.candidates:
        print("没有候选项返回!")
        print("完整响应:", response)
        if hasattr(response, 'prompt_feedback'):
            print("提示反馈:", response.prompt_feedback)
        return
    
    # 检查第一个候选项是否有内容
    if not hasattr(response.candidates[0], 'content') or response.candidates[0].content is None:
        print("候选项没有内容!")
        print("候选项信息:", response.candidates[0])
        if hasattr(response.candidates[0], 'finish_reason'):
            print("完成原因:", response.candidates[0].finish_reason)
        return
    
    # 正常处理响应
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print("文本内容:", part.text[:100] + "..." if len(part.text) > 100 else part.text)
            display(Markdown(part.text))
        elif part.inline_data is not None:
            mime = part.inline_data.mime_type
            print("媒体类型:", mime)
            data = part.inline_data.data
            display(IPythonImage(data=data))

def save_image(response, path):
    if not hasattr(response, 'candidates') or not response.candidates:
        print("没有候选项，无法保存图像")
        return
        
    if not hasattr(response.candidates[0], 'content') or response.candidates[0].content is None:
        print("候选项没有内容，无法保存图像")
        return
        
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            continue
        elif part.inline_data is not None:
            mime = part.inline_data.mime_type
            data = part.inline_data.data
            print(f"处理图像数据，MIME类型: {mime}")
            
            # 检查数据是否为文本格式
            try:
                text_data = data.decode('utf-8', errors='ignore')
                print(f"数据似乎是文本格式，长度: {len(text_data)}")
                print(f"数据前100个字符: {text_data[:100]}...")
                
                # 检查是否为base64编码的图像
                if text_data.startswith('data:image'):
                    print("检测到data URI格式")
                    base64_data = re.sub(r'^data:image/[^;]+;base64,', '', text_data)
                    image_data = base64.b64decode(base64_data)
                    with open(path, 'wb') as f:
                        f.write(image_data)
                    print(f"已从base64 URI解码并保存图像到 {path}")
                    return

                # 检查是否为纯base64
                try:
                    print("尝试解码为纯base64")
                    image_data = base64.b64decode(text_data)
                    with open(path, 'wb') as f:
                        f.write(image_data)
                    print(f"已从纯base64解码并保存图像到 {path}")

                    try:
                        img = PIL.Image.open(path)
                        print(f"成功验证图像: {img.format}, {img.size}")
                        return
                    except Exception as e:
                        print(f"解码后的数据不是有效图像: {e}")
                except Exception as e:
                    print(f"数据不是有效的base64编码: {e}")

                # 检查是否为JSON格式
                try:
                    print("尝试解析为JSON")
                    json_data = json.loads(text_data)
                    if 'image' in json_data:
                        image_data = base64.b64decode(json_data['image'])
                        with open(path, 'wb') as f:
                            f.write(image_data)
                        print(f"已从JSON提取并保存图像到 {path}")
                        return
                except Exception as e:
                    print(f"数据不是有效的JSON格式: {e}")
            except Exception as e:
                print(f"数据不是文本格式: {e}")
            
            print("尝试直接保存原始数据")
            with open(path, 'wb') as f:
                f.write(data)
            print(f"已保存原始数据到 {path}")
            
            # 验证保存的文件
            try:
                img = PIL.Image.open(path)
                print(f"成功验证保存的图像: {img.format}, {img.size}")
            except Exception as e:
                print(f"保存的文件不是有效图像: {e}")

# ... existing code ...

try:
    print("开始执行图像编辑...")
    
    # 检查图像文件是否存在
    image_path = 'nazha.jpg'
    if not os.path.exists(image_path):
        print(f"错误: 图像文件 {image_path} 不存在")
        exit(1)
    
    # 加载图像
    try:
        image = PIL.Image.open(image_path)
        print(f"成功加载图像: {image_path}, 大小: {image.size}, 模式: {image.mode}")
    except Exception as e:
        print(f"加载图像时出错: {e}")
        exit(1)
    
    # 发送请求
    response = client.models.generate_content(
        model="models/gemini-2.0-flash-exp",
        contents=[
            "把猪替换成狗",
            image
        ],
        config=types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE
                )
            ],
            response_modalities=['Text', 'Image']
        )
    )    
    # 检查是否有 IMAGE_SAFETY 问题
    if (hasattr(response, 'candidates') and response.candidates and 
        hasattr(response.candidates[0], 'finish_reason') and 
        str(response.candidates[0].finish_reason) == 'IMAGE_SAFETY'):
        print("检测到图像安全问题: IMAGE_SAFETY")
        print(f"完整的完成原因: {response.candidates[0].finish_reason}")
        print("由于图像安全策略限制，无法处理该图像")
    else:
        # 显示响应
        print("显示响应内容:")
        display_response(response)
        
        # 保存图像
        print("尝试保存图像:")
        save_image(response, 'result.png')
    
    print("处理完成")
    
except Exception as e:
    print(f"发生未处理的异常: {e}")
    traceback.print_exc()