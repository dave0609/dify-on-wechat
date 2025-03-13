from google import genai
from google.genai import types
from PIL import Image
from IPython.display import display, Markdown, Image as IPythonImage
import os
import re
import json
import base64
import PIL

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
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            display(Markdown(part.text))
        elif part.inline_data is not None:
            mime = part.inline_data.mime_type
            print(mime)
            data = part.inline_data.data
            display(IPythonImage(data=data))


def save_image(response, path):
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            continue
        elif part.inline_data is not None:
            mime = part.inline_data.mime_type
            data = part.inline_data.data

            # 检查数据是否为文本格式
            try:
                text_data = data.decode('utf-8', errors='ignore')
                # 检查是否为base64编码的图像
                if text_data.startswith('data:image'):
                    base64_data = re.sub(r'^data:image/[^;]+;base64,', '', text_data)
                    image_data = base64.b64decode(base64_data)
                    with open(path, 'wb') as f:
                        f.write(image_data)
                    print(f"已从base64 URI解码并保存图像到 {path}")
                    return

                # 检查是否为纯base64
                try:
                    image_data = base64.b64decode(text_data)
                    with open(path, 'wb') as f:
                        f.write(image_data)
                    print(f"已从纯base64解码并保存图像到 {path}")

                    try:
                        img = PIL.Image.open(path)
                        print(f"成功验证图像: {img.format}, {img.size}")
                        return
                    except:
                        print("解码后的数据不是有效图像，尝试其他方法")
                except:
                    print("数据不是有效的base64编码")

                # 检查是否为JSON格式
                try:
                    json_data = json.loads(text_data)
                    if 'image' in json_data:
                        image_data = base64.b64decode(json_data['image'])
                        with open(path, 'wb') as f:
                            f.write(image_data)
                        print(f"已从JSON提取并保存图像到 {path}")
                        return
                except:
                    print("数据不是有效的JSON格式")
            except:
                print("数据不是文本格式")

            with open(path, 'wb') as f:
                f.write(data)
            print(f"已保存原始数据到 {path}")

import PIL.Image
image = PIL.Image.open('flying_pig.png')
response = client.models.generate_content(
    model="models/gemini-2.0-flash-exp",
    contents=[
                    "Hey, could you edit this image to make a cat instead of a pig?",
                    image
                ],
    config=types.GenerateContentConfig(
        response_modalities=['Text', 'Image']
    )
)
display_response(response)
save_image(response, 'flying_cat.png')
