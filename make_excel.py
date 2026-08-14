import os
import re
import pandas as pd
from docx import Document

print("🚀 1. 程序已成功启动，正在准备读取 Word 文档...")

# 强制指定你桌面的文件路径（请确保文件叫 500道判断题.docx 并放在桌面上）
input_file = "/Users/mac/Desktop/500道判断题.docx"
output_file = "/Users/mac/Desktop/500道判断题_完美版.xlsx"

# 检查文件到底存不存在
if not os.path.exists(input_file):
    print(f"❌ 错误：在桌面上找不到 {input_file} 这个文件！请检查是不是在桌面上，或者名字有没有多余空格！")
else:
    print("✅ 2. 找到 Word 文档了，正在拼命提取判断题，请稍等几秒钟...")
    try:
        # 读取 Word 文档内容
        doc = Document(input_file)
        text = "\n".join([para.text.strip() for para in doc.paragraphs if para.text.strip()])
        
        # 专门针对“判断题”的精准匹配规则（没有ABCD选项）
        pattern = re.compile(
            r'(\d+\.\s*.*?)\n'            # 匹配：题目
            r'正确答案：(.*?)\n'           # 匹配：正确答案
            r'答案详解：\s*(.*?)\n'         # 匹配：答案详解
            r'难易度：(.*?)(?=\n\d+\.|$)',  # 匹配：难易度
            re.DOTALL
        )
        
        matches = pattern.findall(text)
        
        if not matches:
            print("❌ 错误：打开了文档，但是没有提取到任何题目，请检查文档格式是不是标准。")
        else:
            data = []
            for match in matches:
                q, ans, exp, diff = match
                data.append({
                    "题目": q.strip(),
                    "正确答案": ans.strip(),
                    "答案详解": exp.strip(),
                    "难易度": diff.strip()
                })
                
            print(f"✅ 3. 提取成功！一共抓取到了 {len(data)} 道判断题。正在生成 Excel 表格...")
            
            # 转换为 DataFrame 并导出 Excel
            df = pd.DataFrame(data)
            df.to_excel(output_file, index=False)
            
            print(f"🎉 4. 大功告成！Excel 表格已经存放在你的桌面上了！")
            print(f"📁 文件位置：{output_file}")

    except Exception as e:
        print(f"❌ 运行出现严重错误: {e}")