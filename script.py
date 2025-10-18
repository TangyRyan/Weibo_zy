import requests
from bs4 import BeautifulSoup
import urllib.parse
import json


def get_weibo_ai_search(keyword: str):
    """
    Simulates a request to Weibo's AI search and extracts content from 'card-ai-search_box'.

    Args:
        keyword: The search keyword (without hashtags).

    Returns:
        A list of dictionaries, where each dictionary contains the 'title' and 'content'
        of a 'card-ai-search_box' element. Returns an empty list on failure.
    """
    search_url = 'https://s.weibo.com/ajax_Aidata/search'

    # The keyword is formatted with hashtags and URL-encoded for the referer header
    referer_query = urllib.parse.quote(f"#{keyword}#")

    # Headers are copied from the provided cURL command.
    # Cookies are included in the 'cookie' header.
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'zh-CN,zh;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://s.weibo.com',
        'priority': 'u=1, i',
        'referer': f'https://s.weibo.com/aisearch?q={referer_query}&Refer=weibo_aisearch',
        'sec-ch-ua': '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0',
        'x-requested-with': 'XMLHttpRequest',
        'cookie': 'UOR=www.explinks.com,open.weibo.com,www.explinks.com; SINAGLOBAL=4890265148314.949.1760616647130; SUB=_2A25F9mlkDeRhGeFK6lEY9inFyDuIHXVmiuSsrDV8PUNbmtANLWnFkW9NQ4Q2ECGsYmoj_q5jkQXclOxMddIRxTDq; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9W5hxbQfEQ3wS54quS.PAC4d5JpX5KzhUgL.FoMXeKe4SoM4e0M2dJLoI7DGIg4aPfxWK.U9;'
    }

    # The data payload for the POST request. The query 'q' needs the hashtags.
    data = {
        'q': f"#{keyword}#",
        'page_id': ''
    }

    results = []
    try:
        # Send the POST request
        response = requests.post(search_url, headers=headers, data=data)
        response.raise_for_status()  # Raise an exception for bad status codes

        # The response is JSON, so we parse it first
        json_data = response.json()

        # Check if the API call was successful and data exists
        if json_data.get('code') == '100000' and 'data' in json_data and 'html' in json_data['data']:
            html_content = json_data['data']['html']

            # Use BeautifulSoup to parse the HTML content
            soup = BeautifulSoup(html_content, 'html.parser')

            # Find all divs with the specified class
            search_boxes = soup.find_all('div', class_='card-ai-search_box')

            # Iterate through the found elements and extract the text
            for box in search_boxes:
                title_tag = box.find('div', class_='card-ai-search_titleText')
                content_tag = box.find('div', class_='card-ai-search_content')

                if title_tag and content_tag:
                    results.append({
                        'title': title_tag.get_text(strip=True),
                        'content': content_tag.get_text(strip=True)
                    })

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the request: {e}")
    except json.JSONDecodeError:
        print("Failed to parse JSON from the response.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return results


# --- Main execution block to run the script ---
if __name__ == "__main__":
    # Use the keyword from your example
    search_keyword = "中方回应巴基斯坦向美国赠送稀土"

    extracted_content = get_weibo_ai_search(search_keyword)

    if extracted_content:
        print(
            f"✅ Successfully extracted {len(extracted_content)} AI search boxes for the keyword '{search_keyword}':\n")
        for i, item in enumerate(extracted_content, 1):
            print(f"--- Box {i} ---")
            print(f"Title: {item['title']}")
            print(f"Content: {item['content']}\n")
    else:
        print(f"❌ Could not find any AI search boxes for the keyword '{search_keyword}'. Check cookies or network.")