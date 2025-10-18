import re
import json
import os


def parse_complex_content_to_html(raw_text: str) -> str:
    """
    解析原始文本，但在生成HTML前彻底移除所有引用(wbCustomBlock)和图片/视频(media-block)。

    处理流程：
    1. 移除 <think> 标签。
    2. 移除所有的 ```wbCustomBlock{...}``` 代码块。
    3. 移除所有的 <media-block>...</media-block> 标签。
    4. 将剩余的文本内容转换为格式化的HTML。
    """

    # 步骤 1: 移除 <think> 标签及其所有内容
    processed_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL)

    # 步骤 2: 彻底移除所有 wbCustomBlock 引用块
    processed_text = re.sub(r'```wbCustomBlock\s*({.*?})\s*```', '', processed_text, flags=re.DOTALL)

    # 步骤 3: 彻底移除所有 media-block 媒体块
    processed_text = re.sub(r'<media-block>.*?</media-block>', '', processed_text, flags=re.DOTALL)

    # 步骤 4: 解析剩余的干净文本
    lines = processed_text.split('<br>')
    html_output_lines = []
    in_ul = False
    in_ol = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul: html_output_lines.append('</ul>'); in_ul = False
            if in_ol: html_output_lines.append('</ol>'); in_ol = False

        # 处理标题 (###)
        if line.startswith('### '):
            close_lists()
            title = line.replace('### ', '').strip()
            html_output_lines.append(f'<h3>{title}</h3>')
            continue

        # 处理列表
        if re.match(r'^\d+\.\s', line) or line.strip().startswith('- '):
            list_type = 'ol' if re.match(r'^\d+\.\s', line) else 'ul'

            if list_type == 'ol':
                if not in_ol: close_lists(); html_output_lines.append('<ol>'); in_ol = True
            else:  # ul
                if not in_ul: close_lists(); html_output_lines.append('<ul>'); in_ul = True

            content = re.sub(r'^\d+\.\s*|\-\s*', '', line).strip()
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
            html_output_lines.append(f'<li>{content}</li>')

        else:  # 普通段落
            close_lists()
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            html_output_lines.append(f'<p>{line}</p>')

    close_lists()
    return '\n'.join(html_output_lines)


def create_html_file(content: str, filename: str = "output.html"):
    """将生成的内容包装在完整的HTML模板中，并写入文件。"""

    html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>解析结果 (纯净版)</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 20px auto;
            padding: 0 15px;
            background-color: #f7f7f7;
        }}
        .summarize_text_content {{
            background-color: #ffffff;
            border: 1px solid #e1e1e1;
            border-radius: 8px;
            padding: 20px;
        }}
        h3 {{
            font-size: 1.2em;
            font-weight: bold;
            color: #1a1a1a;
            margin-top: 25px;
            margin-bottom: 15px;
        }}
        p, li {{
            color: #333;
            margin-bottom: 10px;
        }}
        ol, ul {{
            padding-left: 25px;
        }}
        li {{
            margin-bottom: 12px;
        }}
        strong {{
            color: #000;
        }}
    </style>
</head>
<body>
    <div class="summarize_text_content">
        {content}
    </div>
</body>
</html>
"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"成功！不含引用和图片的HTML文件已生成并保存为: {os.path.abspath(filename)}")
    except IOError as e:
        print(f"错误：无法写入文件 {filename}。原因: {e}")

# --- 主程序入口 ---
if __name__ == "__main__":
    # 将您的原始格式文本粘贴到这里
    # 为了可读性，这里使用了多行字符串
    original_content = r"""
    <think><br>嗯，用户查询的是\"中方回应巴基斯坦向美国赠送稀土\"的相关信息。这个问题涉及外交回应、国际关系和稀土战略，需要综合多方信息来回答。<br><br>从搜索结果看，外交部发言人林剑在10月13日的记者会上明确回应了此事。核心信息有三点：第一，所谓\"赠送稀土\"实为宝石原矿样品，巴方工作人员购买的本地宝石原矿；第二，中巴双方在巴美矿产合作上有过沟通，巴方强调绝不会损害中方利益；第三，中国的稀土出口管制措施与巴基斯坦无关，是完善自身出口管理体系的正当做法。<br><br>值得注意的是，多家媒体和自媒体此前传播了不实信息。外交部直接定性这些报道\"或是不了解实情，或是捕风捉影，甚至是挑拨离间\"。胡锡进等大V最初也转发了相关谣言，后在官方澄清后删除内容。<br><br>关于稀土博弈的实质，搜索结果提供了深入背景：中国掌握全球92%的稀土精炼产能，特别是徐光宪院士的萃取技术使中国能生产99.9999%高纯度产品。美国虽试图通过巴基斯坦获取稀土，但缺乏精炼能力，且新建工厂需5-15年。<br><br>用户可能还想了解中巴关系的特殊性。外交部用\"铁杆友谊\"形容两国关系，这种关系建立在共同对抗印度等历史基础上。巴方80%军事装备依赖中国，中巴经济走廊投资达600亿美元，这种深度绑定使得\"背刺\"说法站不住脚。<br><br>对于造谣链条，@玉渊谭天的调查显示，谣言源头是外媒翻炒旧照片，配合社交机器人推高热度。@中国日报则指出，日本经济新闻社控股的《金融时报》最先报道相关消息。<br><br>最后需要提醒，虽然巴方出口的是普通矿产，但中国的新规实际上卡住了稀土的全球供应链。美国军工产业对稀土依赖度达78%，F-35战机每架需417公斤稀土，这解释了为何特朗普会威胁对中国产品加征100%关税。<br><br>在整理回答时，我会把内容分为三部分：外交部回应的核心事实、谣言传播链条分析、稀土博弈的实质。重点突出\"宝石原矿\"与\"稀土样品\"的关键区别，并解释中国稀土技术的不可替代性。对于争议性内容如胡锡进删帖等，会客观陈述事实而不做主观评价。<br></think><br>关于“中方回应巴基斯坦向美国赠送稀土”事件，核心事实与各方分析如下：<br>### ⚖️ 一、外交部官方回应核心要点```wbCustomBlock{\"type\": \"quoted\", \"index\": 2, \"data\": {\"num\": [1, 57, 60, 84], \"version\": 2, \"quote_list\": [{\"name\": \"北京日报\", \"scheme\": \"sinaweibo://detail?mblogid=5221313180336999\", \"index\": 1, \"label\": \"大v\"}, {\"name\": \"环球网\", \"scheme\": \"sinaweibo://detail?mblogid=5221314526184049\", \"index\": 57, \"label\": \"\"}, {\"name\": \"新华社\", \"scheme\": \"sinaweibo://detail?mblogid=5221347733276541\", \"index\": 60, \"label\": \"\"}, {\"name\": \"帝吧官微\", \"scheme\": \"sinaweibo://detail?mblogid=5221321090532557\", \"index\": 84, \"label\": \"\"}], \"name\": \"北京日报\", \"img\": \"https://tvax4.sinaimg.cn/crop.0.0.600.600.50/0024aA4lly8i51bp1z4bcj60go0goq3g02.jpg?KID=imgbed,tva&Expires=1760714530&ssig=04nInI%2FfA%2B\", \"scheme\": \"sinaweibo://detail?mblogid=5221313180336999\", \"vType\": 3}}```<br>1. **事件定性为谣言**  <br>   - **巴方所赠矿石实为宝石原矿**：巴方向美方展示的矿石是工作人员在巴基斯坦当地购买的宝石原矿样品（如蓝宝石、红宝石等），与稀土无关。  <br>   - **中巴保持战略沟通**：关于巴美矿产合作，中巴双方已提前沟通，巴方承诺“绝不会损害中方利益和中巴合作”。  <br>   - **不实报道动机存疑**：外交部批评相关报道“或是不了解实情，或是捕风捉影，甚至是挑拨离间”，缺乏事实依据。<br><br>2. **中国稀土管制与巴基斯坦无关**  <br>   - 中国10月9日发布的稀土开采、冶炼技术出口管制新规，系依据国内法律法规完善出口管理体系的正当行为，旨在履行防扩散义务，与巴基斯坦无任何关联。<media-block><div data-type=\"v\" data-scheme=\"sinaweibo://video/vvs?mid=5221313180336999&multi_paragraph=1&multi_count=0\"><span class=\"arrow\"></span><span class=\"vator\" style=\"display: none;background: url(https://tvax4.sinaimg.cn/crop.0.0.600.600.50/0024aA4lly8i51bp1z4bcj60go0goq3g02.jpg?KID=imgbed,tva&Expires=1760714530&ssig=04nInI%2FfA%2B) no-repeat;background-size: contain;\"></span><span class=\"nick\" style=\"display: none\">北京日报</span><img src=\"http://wx3.sinaimg.cn/middle/0024aA4lly1i6avyazslyj60k00zkgmn02.jpg\" data-width=1280 data-height=720></div></media-block><br>### 🔍 二、谣言传播链条与背景分析```wbCustomBlock{\"type\": \"quoted\", \"index\": 10, \"data\": {\"num\": [19, 43, 44, 64], \"version\": 2, \"quote_list\": [{\"name\": \"环球时报\", \"scheme\": \"sinaweibo://detail?mblogid=5222094594903925\", \"index\": 43, \"label\": \"大v\"}, {\"name\": \"玉渊谭天\", \"scheme\": \"sinaweibo://detail?mblogid=5222105072276414\", \"index\": 19, \"label\": \"\"}, {\"name\": \"中国日报\", \"scheme\": \"sinaweibo://detail?mblogid=5222336548044829\", \"index\": 44, \"label\": \"\"}, {\"name\": \"海风不迷路\", \"scheme\": \"sinaweibo://detail?mblogid=5221378967213417\", \"index\": 64, \"label\": \"\"}], \"name\": \"环球时报\", \"img\": \"https://tvax2.sinaimg.cn/crop.0.0.600.600.50/0029D7FZly8h8vg4kqwr4j60go0got9i02.jpg?KID=imgbed,tva&Expires=1760714531&ssig=g2Ty1VWLT1\", \"scheme\": \"sinaweibo://detail?mblogid=5222094594903925\", \"vType\": 3}}```<br>1. **谣言起源与扩散**  <br>   - 外媒（如英国《金融时报》）炒作“巴基斯坦利用中国技术向美出口稀土”，部分自媒体嫁接“中国反制巴基斯坦”的虚假叙事。```wbCustomBlock{\"type\": \"quoted\", \"index\": 12, \"data\": {\"num\": [64], \"version\": 2, \"quote_list\": [{\"name\": \"海风不迷路\", \"scheme\": \"sinaweibo://detail?mblogid=5221378967213417\", \"index\": 64, \"label\": \"\"}]}}```  <br>   - 白宫照片中的矿石被误读为“稀土样品”，实为普通宝石原矿，且未使用中国技术加工。```wbCustomBlock{\"type\": \"quoted\", \"index\": 13, \"data\": {\"num\": [19, 24], \"version\": 2, \"quote_list\": [{\"name\": \"玉渊谭天\", \"scheme\": \"sinaweibo://detail?mblogid=5222105072276414\", \"index\": 19, \"label\": \"大v\"}, {\"name\": \"孤烟暮蝉\", \"scheme\": \"sinaweibo://detail?mblogid=5221947480474710\", \"index\": 24, \"label\": \"\"}], \"name\": \"玉渊谭天\", \"img\": \"https://tvax3.sinaimg.cn/crop.0.0.600.600.50/007Gut6Lly8hb6eds813lj30go0goweu.jpg?KID=imgbed,tva&Expires=1760714531&ssig=mBXcNagXle\", \"scheme\": \"sinaweibo://detail?mblogid=5222105072276414\", \"vType\": 0}}```<br><br>2. **意图挑拨中巴关系**  <br>   - 境外账号通过社交机器人推高话题热度，在中美贸易磋商敏感期制造矛盾。```wbCustomBlock{\"type\": \"quoted\", \"index\": 15, \"data\": {\"num\": [19, 101], \"version\": 2, \"quote_list\": [{\"name\": \"等待夏天65794\", \"scheme\": \"sinaweibo://detail?mblogid=5222112830948816\", \"index\": 101, \"label\": \"大v\"}, {\"name\": \"玉渊谭天\", \"scheme\": \"sinaweibo://detail?mblogid=5222105072276414\", \"index\": 19, \"label\": \"\"}], \"name\": \"等待夏天65794\", \"img\": \"https://tvax2.sinaimg.cn/crop.0.0.500.500.50/006qih1Aly8gxy6wezvaij30dw0dw40c.jpg?KID=imgbed,tva&Expires=1760714531&ssig=iug9aMMtID\", \"scheme\": \"sinaweibo://detail?mblogid=5222112830948816\", \"vType\": 0}}```  <br>   - 巴基斯坦网友集体发声力挺中国，强调“中巴友谊牢不可破”。```wbCustomBlock{\"type\": \"quoted\", \"index\": 16, \"data\": {\"num\": [24, 88], \"version\": 2, \"quote_list\": [{\"name\": \"孤烟暮蝉\", \"scheme\": \"sinaweibo://detail?mblogid=5221947480474710\", \"index\": 24, \"label\": \"大v\"}, {\"name\": \"孤烟暮蝉\", \"scheme\": \"sinaweibo://detail?mblogid=5221577034826049\", \"index\": 88, \"label\": \"\"}], \"name\": \"孤烟暮蝉\", \"img\": \"https://tvax2.sinaimg.cn/crop.0.0.1080.1080.50/8031f80fly8hdw3sekcbrj20u00u0q94.jpg?KID=imgbed,tva&Expires=1760714531&ssig=9ENGRnNft4\", \"scheme\": \"sinaweibo://detail?mblogid=5221947480474710\", \"vType\": 0}}```<media-block><div data-type=\"v\" data-scheme=\"sinaweibo://video/vvs?mid=5222105072276414&multi_paragraph=2&multi_count=0\"><span class=\"arrow\"></span><span class=\"vator\" style=\"display: none;background: url(https://tvax3.sinaimg.cn/crop.0.0.600.600.50/007Gut6Lly8hb6eds813lj30go0goweu.jpg?KID=imgbed,tva&Expires=1760714531&ssig=mBXcNagXle) no-repeat;background-size: contain;\"></span><span class=\"nick\" style=\"display: none\">玉渊谭天</span><img src=\"http://wx1.sinaimg.cn/middle/007Gut6Lly1i6dc23iolrj31hc0u0b29.jpg\" data-width=1080 data-height=1920></div><div data-type=\"v\" data-scheme=\"sinaweibo://multimedia?mix_mid=5221378967213417&mix_index=0&multi_paragraph=2&multi_count=1\"><span class=\"arrow\"></span><span class=\"vator\" style=\"display: none;background: url(https://tvax3.sinaimg.cn/crop.0.0.1080.1080.50/ab187a00ly8i58x52uq1jj20u00u0gph.jpg?KID=imgbed,tva&Expires=1760714531&ssig=%2FHoBdV9zG7) no-repeat;background-size: contain;\"></span><span class=\"nick\" style=\"display: none\">海风不迷路</span><img src=\"http://wx1.sinaimg.cn/middle/ab187a00ly1i6b06hgzwkj20u01hcdit.jpg\" data-width=1920 data-height=1080></div></media-block><br>### ⚡️ 三、稀土博弈的实质与全球影响```wbCustomBlock{\"type\": \"quoted\", \"index\": 18, \"data\": {\"num\": [11, 31, 35], \"version\": 2, \"quote_list\": [{\"name\": \"这事儿不能说的太细\", \"scheme\": \"sinaweibo://detail?mblogid=5221335611737044\", \"index\": 11, \"label\": \"大v\"}, {\"name\": \"刘成春\", \"scheme\": \"sinaweibo://detail?mblogid=5221405220145806\", \"index\": 31, \"label\": \"\"}, {\"name\": \"墨者善狩本人\", \"scheme\": \"sinaweibo://detail?mblogid=5221577303261958\", \"index\": 35, \"label\": \"\"}], \"name\": \"这事儿不能说的太细\", \"img\": \"https://tvax4.sinaimg.cn/crop.0.0.765.765.50/008z5nOKly8ho8zbiq4btj30l90l9401.jpg?KID=imgbed,tva&Expires=1760714530&ssig=UtgmagHLbC\", \"scheme\": \"sinaweibo://detail?mblogid=5221335611737044\", \"vType\": 0}}```<br>1. **中国稀土技术不可替代**  <br>   - **提纯技术垄断**：中国掌握全球85%的稀土精炼产能，徐光宪院士的串级萃取技术可实现99.9999%超高纯度，成本仅为西方1/3。```wbCustomBlock{\"type\": \"quoted\", \"index\": 20, \"data\": {\"num\": [11, 35], \"version\": 2, \"quote_list\": [{\"name\": \"墨者善狩本人\", \"scheme\": \"sinaweibo://detail?mblogid=5221577303261958\", \"index\": 35, \"label\": \"大v\"}, {\"name\": \"这事儿不能说的太细\", \"scheme\": \"sinaweibo://detail?mblogid=5221335611737044\", \"index\": 11, \"label\": \"\"}], \"name\": \"墨者善狩本人\", \"img\": \"https://tva3.sinaimg.cn/crop.40.13.284.284.50/730e25fbgw1fbney811yoj20ck08bt9d.jpg?KID=imgbed,tva&Expires=1760714531&ssig=pS2E6gvth0\", \"scheme\": \"sinaweibo://detail?mblogid=5221577303261958\", \"vType\": 0}}```  <br>   - **全产业链控制**：从开采、分离到永磁体制造，中国拥有完整产业链，美国军工（如F-35战机）78%的稀土依赖中国供应。```wbCustomBlock{\"type\": \"quoted\", \"index\": 21, \"data\": {\"num\": [31], \"version\": 2, \"quote_list\": [{\"name\": \"刘成春\", \"scheme\": \"sinaweibo://detail?mblogid=5221405220145806\", \"index\": 31, \"label\": \"大v\"}], \"name\": \"刘成春\", \"img\": \"https://tvax1.sinaimg.cn/crop.0.0.690.690.50/5f57cbd5ly8h289mu0a6hj20j60j6wgj.jpg?KID=imgbed,tva&Expires=1760714531&ssig=%2FeH%2Fkrbfuy\", \"scheme\": \"sinaweibo://detail?mblogid=5221405220145806\", \"vType\": 0}}```<br><br>2. **美巴合作的实际局限**  <br>   - **巴基斯坦无精炼能力**：巴方仅能出口原矿或粗加工产品，精炼需依赖中国技术授权。```wbCustomBlock{\"type\": \"quoted\", \"index\": 23, \"data\": {\"num\": [35, 90], \"version\": 2, \"quote_list\": [{\"name\": \"墨者善狩本人\", \"scheme\": \"sinaweibo://detail?mblogid=5221577303261958\", \"index\": 35, \"label\": \"\"}, {\"name\": \"不会做梦的小鱼\", \"scheme\": \"sinaweibo://detail?mblogid=5221213469147911\", \"index\": 90, \"label\": \"\"}]}}```  <br>   - **美国供应链困境**：美企在巴建厂面临电力短缺、安保成本高、基建滞后等难题，且5年内难以突破技术壁垒。```wbCustomBlock{\"type\": \"quoted\", \"index\": 24, \"data\": {\"num\": [87], \"version\": 2, \"quote_list\": [{\"name\": \"南巷的风NF\", \"scheme\": \"sinaweibo://detail?mblogid=5221340558656382\", \"index\": 87, \"label\": \"\"}]}}```<br><br>3. **中巴关系的战略根基**  <br>   - **经济深度绑定**：中巴经济走廊（CPEC）投资超600亿美元，占巴外资总额80%，美国5亿美元矿产投资规模远无法比拟。```wbCustomBlock{\"type\": \"quoted\", \"index\": 26, \"data\": {\"num\": [29], \"version\": 2, \"quote_list\": [{\"name\": \"张胜军\", \"scheme\": \"sinaweibo://detail?mblogid=5221568608208941\", \"index\": 29, \"label\": \"\"}]}}```  <br>   - **地缘安全互信**：巴基斯坦80%军事装备由中国提供，双方在抗衡印度、反恐等领域高度协同。```wbCustomBlock{\"type\": \"quoted\", \"index\": 27, \"data\": {\"num\": [61, 92], \"version\": 2, \"quote_list\": [{\"name\": \"阿卡宇航\", \"scheme\": \"sinaweibo://detail?mblogid=5221328069856932\", \"index\": 92, \"label\": \"大v\"}, {\"name\": \"王强老师\", \"scheme\": \"sinaweibo://detail?mblogid=5221328225568702\", \"index\": 61, \"label\": \"\"}], \"name\": \"阿卡宇航\", \"img\": \"https://tvax3.sinaimg.cn/crop.0.0.1080.1080.50/0089Nbwdly8h8uhciiaqnj30u00u0jsh.jpg?KID=imgbed,tva&Expires=1760714531&ssig=R928MkFicI\", \"scheme\": \"sinaweibo://detail?mblogid=5221328069856932\", \"vType\": 0}}```<media-block><div data-type=\"v\" data-scheme=\"sinaweibo://video/vvs?mid=5221335611737044&multi_paragraph=3&multi_count=0\"><span class=\"arrow\"></span><span class=\"vator\" style=\"display: none;background: url(https://tvax4.sinaimg.cn/crop.0.0.765.765.50/008z5nOKly8ho8zbiq4btj30l90l9401.jpg?KID=imgbed,tva&Expires=1760714530&ssig=UtgmagHLbC) no-repeat;background-size: contain;\"></span><span class=\"nick\" style=\"display: none\">这事儿不能说的太细</span><img src=\"http://wx2.sinaimg.cn/middle/008z5nOKgy1i6aut7lb6jj30u00gvtds.jpg\" data-width=607 data-height=1080></div><div data-type=\"v\" data-scheme=\"sinaweibo://video/vvs?mid=5221328225568702&multi_paragraph=3&multi_count=1\"><span class=\"arrow\"></span><span class=\"vator\" style=\"display: none;background: url(https://tvax3.sinaimg.cn/crop.0.0.796.796.50/008s2Uynly8h8mbjcswgkj30m40m4ab2.jpg?KID=imgbed,tva&Expires=1760714531&ssig=oeIwHRulls) no-repeat;background-size: contain;\"></span><span class=\"nick\" style=\"display: none\">王强老师</span><img src=\"http://wx1.sinaimg.cn/middle/008s2Uynly1i6aubvbvihj31hc0u01ky.jpg\" data-width=1080 data-height=1920></div></media-block><br>### 💎 结论与启示<br>1. **谣言止于权威**：外交部及时辟谣凸显中巴高度互信，挑拨企图未动摇两国“铁杆友谊”。```wbCustomBlock{\"type\": \"quoted\", \"index\": 30, \"data\": {\"num\": [79, 83], \"version\": 2, \"quote_list\": [{\"name\": \"沈逸\", \"scheme\": \"sinaweibo://detail?mblogid=5221331685870618\", \"index\": 79, \"label\": \"大v\"}, {\"name\": \"后沙月光本尊\", \"scheme\": \"sinaweibo://detail?mblogid=5221333755760096\", \"index\": 83, \"label\": \"\"}], \"name\": \"沈逸\", \"img\": \"https://tva2.sinaimg.cn/crop.564.1.371.371.50/45039c9ajw1e6iw505q0jj20qy0ae0v1.jpg?KID=imgbed,tva&Expires=1760714531&ssig=gL9ysfg3k3\", \"scheme\": \"sinaweibo://detail?mblogid=5221331685870618\", \"vType\": 0}}```  <br>2. **稀土博弈本质是技术主导权**：中国通过管制精准反制美国“去中国化”供应链计划，直击其军工和新能源产业痛点。```wbCustomBlock{\"type\": \"quoted\", \"index\": 31, \"data\": {\"num\": [36, 67], \"version\": 2, \"quote_list\": [{\"name\": \"魏叔胡侃ws\", \"scheme\": \"sinaweibo://detail?mblogid=5221646643757594\", \"index\": 36, \"label\": \"\"}, {\"name\": \"仰望弗洛伊德\", \"scheme\": \"sinaweibo://detail?mblogid=5221364483234419\", \"index\": 67, \"label\": \"\"}]}}```  <br>3. **警惕信息战新形态**：敏感时期需甄别境外势力操纵的虚假叙事，以事实反击舆论攻击。```wbCustomBlock{\"type\": \"quoted\", \"index\": 32, \"data\": {\"num\": [45, 89], \"version\": 2, \"quote_list\": [{\"name\": \"老王谈改革\", \"scheme\": \"sinaweibo://detail?mblogid=5221546255713621\", \"index\": 45, \"label\": \"\"}, {\"name\": \"葵视界\", \"scheme\": \"sinaweibo://detail?mblogid=5221350525632665\", \"index\": 89, \"label\": \"\"}], \"name\": \"老王谈改革\", \"img\": \"https://tvax2.sinaimg.cn/crop.0.0.329.329.50/947597a8ly8hj8wtuu5saj2095095weh.jpg?KID=imgbed,tva&Expires=1760714531&ssig=ncbSuhbbMz\", \"scheme\": \"sinaweibo://detail?mblogid=5221546255713621\", \"vType\": 0}}```<media-block><div data-type=\"v\" data-scheme=\"sinaweibo://video/vvs?mid=5221364483234419&multi_paragraph=4&multi_count=0\"><span class=\"arrow\"></span><span class=\"vator\" style=\"display: none;background: url(https://tvax1.sinaimg.cn/crop.0.0.512.512.50/c5205aa1ly8fy7nieizuqj20e80e8aao.jpg?KID=imgbed,tva&Expires=1760714531&ssig=i6DQoVXgAS) no-repeat;background-size: contain;\"></span><span class=\"nick\" style=\"display: none\">仰望弗洛伊德</span><img src=\"http://wx1.sinaimg.cn/middle/c5205aa1ly1i6ayhm2r4qj21hc0u00ud.jpg\" data-width=1080 data-height=1920></div></media-block><br>
    """
    raw_text = parse_complex_content_to_html(original_content)
    create_html_file(raw_text)