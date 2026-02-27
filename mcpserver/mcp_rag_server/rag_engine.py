"""
RAG Engine
支持多种检索策略：基础检索、Query Rewrite、Rerank、Hybrid Search
"""
import asyncio
import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import httpx
from openai import OpenAI, AsyncOpenAI
from pinecone import Pinecone

from config import config

# Embedding / LLM 请求超时 (连接5s, 读取20s)
_API_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
_EMBEDDING_MAX_RETRIES = 2


@dataclass
class SearchResult:
    """检索结果"""
    text: str
    source: str
    score: float
    metadata: dict = None


class RAGEngine:
    """RAG 引擎，支持多种检索策略"""

    def __init__(self):
        # Embedding 客户端 (带严格超时)
        self.embedding_client = OpenAI(
            api_key=config.embedding_api_key,
            base_url=config.embedding_base_url,
            timeout=_API_TIMEOUT,
            max_retries=0,  # 我们自己控制重试
        )

        # LLM 客户端 (用于 rewrite/rerank)
        self.llm_client = AsyncOpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            timeout=_API_TIMEOUT,
            max_retries=0,
        )

        # Pinecone
        self.pc = Pinecone(api_key=config.pinecone_api_key)
        self.index = self.pc.Index(host=config.pinecone_host)

        # BM25 索引 (简化版，实际使用建议用 Elasticsearch 或 rank_bm25)
        self._bm25_index = None

    # ==================== 基础能力 ====================

    def get_embedding(self, text: str) -> List[float]:
        """生成 embedding (带重试)"""
        text = text.replace("\n", " ")
        last_err = None
        for attempt in range(_EMBEDDING_MAX_RETRIES + 1):
            try:
                response = self.embedding_client.embeddings.create(
                    input=[text],
                    model=config.embedding_model,
                    extra_body={"input_type": "query", "truncate": "END"},
                )
                return response.data[0].embedding
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_err = e
                if attempt < _EMBEDDING_MAX_RETRIES:
                    time.sleep(1)
        raise last_err

    def _query_pinecone(self, embedding: List[float], top_k: int) -> List[Dict]:
        """查询 Pinecone"""
        results = self.index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True,
            include_values=False
        )

        items = []
        for match in results.get('matches', []):
            metadata = match.get('metadata', {})
            items.append({
                "id": match.get('id', ''),
                "text": metadata.get('text', ''),
                "source": metadata.get('filename', 'unknown'),
                "score": match.get('score', 0),
                "metadata": metadata
            })
        return items

    # ==================== 检索策略 ====================

    async def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """基础向量检索"""
        start = time.time()

        embedding = self.get_embedding(query)
        results = self._query_pinecone(embedding, top_k)

        return {
            "strategy": "basic",
            "query": query,
            "results": results,
            "latency_ms": int((time.time() - start) * 1000)
        }

    async def search_with_rewrite(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """带 Query Rewrite 的检索"""
        start = time.time()

        # Step 1: Query Rewrite
        rewritten = await self._rewrite_query(query)

        # Step 2: 检索
        embedding = self.get_embedding(rewritten["rewritten_query"])
        results = self._query_pinecone(embedding, top_k)

        return {
            "strategy": "rewrite",
            "original_query": query,
            "rewritten_query": rewritten["rewritten_query"],
            "rewrite_explanation": rewritten.get("explanation", ""),
            "results": results,
            "latency_ms": int((time.time() - start) * 1000)
        }

    async def search_with_rerank(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """带 Rerank 的检索"""
        start = time.time()

        # Step 1: 先取更多候选
        candidate_k = top_k * config.rerank_candidate_multiplier
        embedding = self.get_embedding(query)
        candidates = self._query_pinecone(embedding, candidate_k)

        # Step 2: Rerank
        if candidates:
            reranked = await self._rerank(query, candidates)
            results = reranked[:top_k]
        else:
            results = []

        return {
            "strategy": "rerank",
            "query": query,
            "candidates_count": len(candidates),
            "results": results,
            "latency_ms": int((time.time() - start) * 1000)
        }

    async def search_hybrid(
        self,
        query: str,
        top_k: int = 5,
        bm25_weight: float = 0.3
    ) -> Dict[str, Any]:
        """混合检索 (Embedding + BM25)"""
        start = time.time()

        # Embedding 检索
        embedding = self.get_embedding(query)
        embedding_results = self._query_pinecone(embedding, top_k * 2)

        # BM25 检索 (简化版：基于关键词匹配打分)
        bm25_results = await self._bm25_search(query, embedding_results)

        # 融合分数
        fused = self._fuse_results(
            embedding_results,
            bm25_results,
            bm25_weight=bm25_weight
        )

        return {
            "strategy": "hybrid",
            "query": query,
            "bm25_weight": bm25_weight,
            "embedding_weight": 1 - bm25_weight,
            "results": fused[:top_k],
            "latency_ms": int((time.time() - start) * 1000)
        }

    async def search_full(
        self,
        query: str,
        top_k: int = 5,
        bm25_weight: float = 0.3,
        show_debug: bool = False,
        skip_rewrite: bool = None,
        skip_rerank: bool = None
    ) -> Dict[str, Any]:
        """完整 RAG 流程: Rewrite → Hybrid → Rerank"""
        start = time.time()
        debug_info = {}

        # 判断是否跳过 rewrite（参数优先，否则看 config）
        should_skip_rewrite = skip_rewrite if skip_rewrite is not None else config.skip_rewrite
        # 判断是否跳过 rerank（参数优先，否则看 config）
        should_skip_rerank = skip_rerank if skip_rerank is not None else config.skip_rerank

        # Step 1: Query Rewrite (可跳过)
        if should_skip_rewrite:
            rewritten_query = query
            if show_debug:
                debug_info["rewrite"] = {"skipped": True, "reason": "skip_rewrite enabled"}
        else:
            rewritten = await self._rewrite_query(query)
            rewritten_query = rewritten["rewritten_query"]
            if show_debug:
                debug_info["rewrite"] = rewritten

        # Step 2: Hybrid Search (embedding 失败时降级为空结果)
        # 关键：用 to_thread 避免同步调用阻塞 MCP server 事件循环
        candidate_k = top_k * config.rerank_candidate_multiplier
        embedding_results = []
        try:
            embedding = await asyncio.to_thread(self.get_embedding, rewritten_query)
            embedding_results = await asyncio.to_thread(self._query_pinecone, embedding, candidate_k)
        except Exception as e:
            if show_debug:
                debug_info["embedding_error"] = str(e)

        if embedding_results:
            bm25_results = await self._bm25_search(rewritten_query, embedding_results)
            fused = self._fuse_results(embedding_results, bm25_results, bm25_weight)
        else:
            fused = []

        if show_debug:
            debug_info["hybrid_candidates"] = len(fused)

        # Step 3: Rerank (可跳过)
        if should_skip_rerank:
            results = fused[:top_k]
            if show_debug:
                debug_info["rerank"] = {"skipped": True, "reason": "skip_rerank enabled"}
        elif fused:
            reranked = await self._rerank(rewritten_query, fused)
            results = reranked[:top_k]
        else:
            results = []

        output = {
            "strategy": "full",
            "original_query": query,
            "rewritten_query": rewritten_query,
            "results": results,
            "latency_ms": int((time.time() - start) * 1000)
        }

        if show_debug:
            output["debug"] = debug_info

        return output

    # ==================== 对比和调试 ====================

    async def compare_strategies(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """对比多种检索策略"""
        results = {}

        # 基础检索
        results["basic"] = await self.search(query, top_k)

        # Query Rewrite
        results["rewrite"] = await self.search_with_rewrite(query, top_k)

        # Rerank
        results["rerank"] = await self.search_with_rerank(query, top_k)

        # Hybrid
        results["hybrid"] = await self.search_hybrid(query, top_k)

        # Full
        results["full"] = await self.search_full(query, top_k)

        # 对比分析
        analysis = self._analyze_comparison(results)

        return {
            "query": query,
            "strategies": results,
            "analysis": analysis
        }

    async def debug_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """调试查询"""
        embedding = self.get_embedding(query)
        results = self._query_pinecone(embedding, top_k)

        # 分数分布
        scores = [r["score"] for r in results]
        score_stats = {
            "max": max(scores) if scores else 0,
            "min": min(scores) if scores else 0,
            "avg": sum(scores) / len(scores) if scores else 0,
            "spread": max(scores) - min(scores) if scores else 0
        }

        # 来源分布
        sources = {}
        for r in results:
            src = r["source"]
            sources[src] = sources.get(src, 0) + 1

        return {
            "query": query,
            "embedding_preview": embedding[:10],  # 只显示前10维
            "embedding_dim": len(embedding),
            "results_count": len(results),
            "score_distribution": score_stats,
            "source_distribution": sources,
            "results": results
        }

    async def evaluate_query(
        self,
        query: str,
        expected_keywords: List[str] = None,
        expected_sources: List[str] = None
    ) -> Dict[str, Any]:
        """评估查询质量"""
        result = await self.search(query, top_k=10)
        results = result["results"]

        eval_result = {
            "query": query,
            "retrieved_count": len(results)
        }

        # 关键词召回评估
        if expected_keywords:
            all_text = " ".join([r["text"] for r in results])
            hits = [kw for kw in expected_keywords if kw.lower() in all_text.lower()]
            eval_result["keyword_recall"] = {
                "expected": expected_keywords,
                "hits": hits,
                "recall_rate": len(hits) / len(expected_keywords) if expected_keywords else 0
            }

        # 来源召回评估
        if expected_sources:
            retrieved_sources = set(r["source"] for r in results)
            hits = [src for src in expected_sources if src in retrieved_sources]
            eval_result["source_recall"] = {
                "expected": expected_sources,
                "hits": hits,
                "recall_rate": len(hits) / len(expected_sources) if expected_sources else 0
            }

        return eval_result

    # ==================== 内部方法 ====================

    async def _rewrite_query(self, query: str) -> Dict[str, str]:
        """Query Rewrite"""
        prompt = f"""你是一个查询改写专家。将用户的口语化查询转换为更适合检索哲学知识库的形式。

用户查询: {query}

改写规则:
1. 将口语转换为学术/哲学术语
2. 添加相关的同义词或概念
3. 保持原意，不要过度扩展

输出 JSON:
{{"rewritten_query": "改写后的查询", "explanation": "改写说明"}}"""

        response = await self.llm_client.chat.completions.create(
            model=config.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )

        content = response.choices[0].message.content
        try:
            # 清理可能的 markdown
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content.strip())
        except:
            return {"rewritten_query": query, "explanation": "改写失败，使用原查询"}

    async def _rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """使用 LLM 重排"""
        if not candidates:
            return []

        # 构建候选列表
        candidates_text = "\n".join([
            f"[{i}] {c['text'][:300]}"
            for i, c in enumerate(candidates[:15])  # 最多15个候选
        ])

        prompt = f"""根据查询的相关性，对以下文本片段重新排序。

查询: {query}

候选文本:
{candidates_text}

按相关性从高到低输出编号，用逗号分隔，如: 3,1,5,2,4
只输出编号序列，不要其他内容。"""

        response = await self.llm_client.chat.completions.create(
            model=config.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100
        )

        try:
            order_str = response.choices[0].message.content.strip()
            order = [int(x.strip()) for x in order_str.split(",") if x.strip().isdigit()]

            # 按新顺序排列
            reranked = []
            for idx in order:
                if 0 <= idx < len(candidates):
                    item = candidates[idx].copy()
                    item["rerank_position"] = len(reranked) + 1
                    reranked.append(item)

            # 添加未被排序的
            seen = set(order)
            for i, c in enumerate(candidates):
                if i not in seen:
                    item = c.copy()
                    item["rerank_position"] = len(reranked) + 1
                    reranked.append(item)

            return reranked

        except:
            return candidates

    async def _bm25_search(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """简化版 BM25 (基于词频)"""
        # 分词 (简单按空格和标点)
        import re
        query_terms = set(re.findall(r'[\w\u4e00-\u9fff]+', query.lower()))

        scored = []
        for c in candidates:
            text = c.get("text", "").lower()
            text_terms = set(re.findall(r'[\w\u4e00-\u9fff]+', text))

            # 计算重叠
            overlap = len(query_terms & text_terms)
            bm25_score = overlap / (len(query_terms) + 1)  # 简化的 BM25

            item = c.copy()
            item["bm25_score"] = bm25_score
            scored.append(item)

        return sorted(scored, key=lambda x: x["bm25_score"], reverse=True)

    def _fuse_results(
        self,
        embedding_results: List[Dict],
        bm25_results: List[Dict],
        bm25_weight: float = 0.3
    ) -> List[Dict]:
        """融合 embedding 和 BM25 结果"""
        embedding_weight = 1 - bm25_weight

        # 建立 id -> scores 映射
        scores = {}
        for i, r in enumerate(embedding_results):
            rid = r.get("id", str(i))
            # 归一化排名分数
            embedding_rank_score = 1 / (i + 1)
            scores[rid] = {
                "item": r,
                "embedding_score": embedding_rank_score,
                "bm25_score": 0
            }

        for i, r in enumerate(bm25_results):
            rid = r.get("id", str(i))
            bm25_rank_score = 1 / (i + 1)
            if rid in scores:
                scores[rid]["bm25_score"] = bm25_rank_score
            else:
                scores[rid] = {
                    "item": r,
                    "embedding_score": 0,
                    "bm25_score": bm25_rank_score
                }

        # 计算融合分数
        fused = []
        for rid, data in scores.items():
            item = data["item"].copy()
            item["fused_score"] = (
                data["embedding_score"] * embedding_weight +
                data["bm25_score"] * bm25_weight
            )
            fused.append(item)

        return sorted(fused, key=lambda x: x["fused_score"], reverse=True)

    def _analyze_comparison(self, results: Dict) -> Dict:
        """分析对比结果"""
        analysis = {}

        # 提取每种策略的 top-1 结果
        for strategy, data in results.items():
            if data.get("results"):
                top1 = data["results"][0]
                analysis[strategy] = {
                    "top1_source": top1.get("source"),
                    "top1_score": top1.get("score"),
                    "latency_ms": data.get("latency_ms")
                }

        # 检查结果一致性
        top1_sources = [a.get("top1_source") for a in analysis.values()]
        analysis["consistency"] = len(set(top1_sources)) == 1

        return analysis
