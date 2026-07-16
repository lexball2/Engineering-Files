"""AI 自动分类——上传文档时自动判断属于哪个分类"""
import logging
from functools import lru_cache
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from backend.config import settings

logger = logging.getLogger(__name__)

# 可后续替换为数据库动态读取
CATEGORIES = [
    "制度文件", "培训资料", "产品文档", "工作报告", "技术文档", "其他"
]

# 结构化输出模型，强制规范返回
class CategoryOutput(BaseModel):
    category: str = Field(description="文档匹配分类，必须从给定列表选择")

parser = PydanticOutputParser(pydantic_object=CategoryOutput)

@lru_cache(maxsize=1)
def _get_classifier_llm():
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=0,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=15,
        max_retries=2,
    )

CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是文档分类助手，根据文档内容选择唯一匹配分类。
可选分类列表：{categories}
输出JSON格式，仅包含category字段，不要额外文字。
{format_instructions}"""),
    ("human", "文档摘要内容：\n{text}"),
])

def classify_document(text: str) -> str:
    summary = text[:800].strip()
    if not summary:
        return "其他"
    llm = _get_classifier_llm()
    cat_str = "、".join(CATEGORIES)
    prompt = CLASSIFY_PROMPT.partial(format_instructions=parser.get_format_instructions())
    chain = prompt | llm | parser
    try:
        res: CategoryOutput = chain.invoke({"categories": cat_str, "text": summary})
        cat = res.category.strip()
        if cat not in CATEGORIES:
            logger.warning(f"无效分类 {cat}，兜底其他")
            return "其他"
        logger.info(f"文档自动分类：{cat}")
        return cat
    except Exception as e:
        logger.error(f"分类调用失败：{str(e)}", exc_info=True)
        return "其他"

def classify_and_tag(chunks: List) -> str:
    if not chunks:
        return "其他"
    content = " ".join(d.page_content.strip() for d in chunks[:3] if d.page_content.strip())
    return classify_document(content)