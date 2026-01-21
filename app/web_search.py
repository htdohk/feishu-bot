"""
联网搜索和网页内容获取模块
支持从网页获取内容和调用搜索引擎
"""
import logging
import re
from typing import Optional, Dict, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import config

logger = logging.getLogger("feishu_bot.web_search")


async def fetch_webpage_content(url: str, max_length: int = 5000) -> Tuple[Optional[str], Optional[str]]:
    """
    获取网页内容
    
    Args:
        url: 网页 URL
        max_length: 最大内容长度
        
    Returns:
        (内容, 错误信息) 元组
    """
    if not url:
        return None, "URL 为空"
    
    # 验证 URL 格式
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    try:
        # 验证 URL 有效性
        parsed = urlparse(url)
        if not parsed.netloc:
            return None, "无效的 URL 格式"
    except Exception as e:
        return None, f"URL 解析失败: {str(e)}"
    
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            if resp.status_code >= 400:
                return None, f"HTTP {resp.status_code}"
            
            # 尝试检测编码
            content_type = resp.headers.get("content-type", "")
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
                try:
                    text = resp.content.decode(charset)
                except:
                    text = resp.text
            else:
                text = resp.text
            
            # 解析 HTML
            soup = BeautifulSoup(text, "html.parser")
            
            # 移除脚本和样式
            for script in soup(["script", "style", "meta", "link"]):
                script.decompose()
            
            # 获取主要内容
            # 优先级：article > main > content > body
            main_content = None
            for selector in ["article", "main", "[role='main']", ".content", ".main-content"]:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if not main_content:
                main_content = soup.body or soup
            
            # 提取文本
            text_content = main_content.get_text(separator="\n", strip=True)
            
            # 清理多余空白
            lines = [line.strip() for line in text_content.split("\n") if line.strip()]
            text_content = "\n".join(lines)
            
            # 限制长度
            if len(text_content) > max_length:
                text_content = text_content[:max_length] + "...[内容已截断]"
            
            logger.info(f"fetch_webpage_content url={url} content_len={len(text_content)}")
            return text_content, None
            
    except httpx.TimeoutException:
        return None, "请求超时"
    except Exception as e:
        logger.error(f"fetch_webpage_content error: {e}")
        return None, f"获取失败: {str(e)[:100]}"


async def search_with_searxng(query: str, num_results: int = 5) -> Tuple[Optional[str], Optional[str]]:
    """
    使用 Searxng 搜索
    
    Args:
        query: 搜索查询
        num_results: 返回结果数
        
    Returns:
        (搜索结果, 错误信息) 元组
    """
    if not query or not query.strip():
        return None, "搜索查询为空"
    
    try:
        async with httpx.AsyncClient(timeout=config.SEARXNG_TIMEOUT) as client:
            params = {
                "q": query,
                "format": "json",
                "pageno": 1,
                "results": num_results
            }
            
            resp = await client.get(f"{config.SEARXNG_URL}/search", params=params)
            
            if resp.status_code >= 400:
                return None, f"搜索服务错误: HTTP {resp.status_code}"
            
            data = resp.json()
            results = data.get("results", [])
            
            if not results:
                return None, "未找到相关结果"
            
            # 格式化结果
            formatted_results = []
            for i, result in enumerate(results[:num_results], 1):
                title = result.get("title", "")
                url = result.get("url", "")
                snippet = result.get("content", "")
                
                formatted_results.append(
                    f"{i}. {title}\n"
                    f"   链接: {url}\n"
                    f"   摘要: {snippet[:200]}"
                )
            
            result_text = "\n\n".join(formatted_results)
            logger.info(f"search_with_searxng query='{query}' results={len(results)}")
            return result_text, None
            
    except httpx.TimeoutException:
        return None, "搜索超时"
    except Exception as e:
        logger.error(f"search_with_searxng error: {e}")
        return None, f"搜索失败: {str(e)[:100]}"


def extract_urls_from_text(text: str) -> list[str]:
    """
    从文本中提取 URL
    
    Args:
        text: 文本内容
        
    Returns:
        URL 列表
    """
    # 简单的 URL 正则表达式
    url_pattern = r'https?://[^\s\)\]\}]+'
    urls = re.findall(url_pattern, text)
    return list(set(urls))  # 去重


async def process_urls_in_context(text: str, max_urls: int = 3) -> Dict[str, str]:
    """
    处理文本中的 URL，获取网页内容
    
    Args:
        text: 包含 URL 的文本
        max_urls: 最多处理的 URL 数
        
    Returns:
        {url: content} 字典
    """
    urls = extract_urls_from_text(text)
    
    if not urls:
        return {}
    
    url_contents = {}
    for url in urls[:max_urls]:
        content, error = await fetch_webpage_content(url)
        if content:
            url_contents[url] = content
        else:
            logger.warning(f"Failed to fetch {url}: {error}")
    
    return url_contents


async def should_use_web_search(text: str, context: str = "") -> bool:
    """
    使用语义识别判断是否需要网络搜索
    
    Args:
        text: 用户输入文本
        context: 群聊上下文
        
    Returns:
        是否需要搜索
    """
    from .semantic_intent import detect_user_intent
    
    # 使用 LLM 进行语义识别
    intent_result = await detect_user_intent(text, context)
    intent = intent_result.get("intent", "chat")
    details = intent_result.get("details", {})
    
    # 如果是提问类意图，检查是否需要搜索
    if intent == "question":
        # 检查是否涉及实时信息、事实查询等需要搜索的内容
        description = details.get("description", "").lower()
        search_indicators = [
            "最新", "实时", "当前", "现在", "今天", "最近",
            "查询", "了解", "是什么", "怎么样", "有哪些",
            "latest", "current", "today", "recent", "what is", "how"
        ]
        return any(indicator in description for indicator in search_indicators)
    
    return False
