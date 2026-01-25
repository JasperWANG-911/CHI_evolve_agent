"""
Function Library Manager - 管理函数库的持久化和动态扩展

职责:
1. 加载不同级别的内置函数
2. 加载已批准的自定义函数
3. 管理待审核函数的提交和状态
4. 生成函数摘要供Coding Agent使用
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from .registry import (
    FunctionRegistry,
    FunctionInfo,
    FunctionLevel,
    ParameterInfo,
    get_registry
)


@dataclass
class PendingFunction:
    """待审核的函数"""
    pr_id: str
    function_name: str
    function_code: str
    description: str
    parameters: List[Dict[str, Any]]
    returns: str
    context: str  # 为什么需要这个函数
    submitted_at: str
    status: str  # "pending_pr_review" | "pending_human_review" | "approved" | "rejected"
    pr_review_result: Optional[Dict[str, Any]] = None
    human_decision: Optional[str] = None  # "approve" | "reject"
    human_comment: Optional[str] = None


@dataclass
class ApprovedFunction:
    """已批准的自定义函数"""
    function_name: str
    function_code: str
    description: str
    parameters: List[Dict[str, Any]]
    returns: str
    approved_at: str
    pr_id: str  # 原始PR ID


class FunctionLibraryManager:
    """函数库管理器"""

    def __init__(self,
                 project_root: Optional[Path] = None,
                 initial_level: FunctionLevel = FunctionLevel.FULL):
        """
        初始化函数库管理器

        Args:
            project_root: 项目根目录
            initial_level: 初始函数库级别 (MINIMAL, PARTIAL, FULL)
        """
        self.project_root = project_root or Path(__file__).parent.parent
        self.current_level = initial_level
        self.registry = get_registry()

        # 路径配置
        self.function_library_dir = self.project_root / "function_library"
        self.approved_dir = self.function_library_dir / "approved"
        self.pending_dir = self.function_library_dir / "pending"
        self.review_queue_dir = self.project_root / "review_queue"

        # 确保目录存在
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.review_queue_dir.mkdir(parents=True, exist_ok=True)

        # 加载已批准的自定义函数
        self._approved_functions: Dict[str, ApprovedFunction] = {}
        self._load_approved_functions()

    def _load_approved_functions(self):
        """加载已批准的自定义函数"""
        index_path = self.approved_dir / "index.json"
        if not index_path.exists():
            # 创建空索引
            self._save_approved_index()
            return

        with open(index_path, 'r') as f:
            data = json.load(f)

        for func_data in data.get("functions", []):
            func = ApprovedFunction(**func_data)
            self._approved_functions[func.function_name] = func

    def _save_approved_index(self):
        """保存已批准函数索引"""
        index_path = self.approved_dir / "index.json"
        data = {
            "functions": [asdict(f) for f in self._approved_functions.values()],
            "updated_at": datetime.now().isoformat()
        }
        with open(index_path, 'w') as f:
            json.dump(data, f, indent=2)

    def set_level(self, level: FunctionLevel):
        """设置当前函数库级别"""
        self.current_level = level

    def get_available_function_names(self) -> List[str]:
        """获取当前可用的所有函数名"""
        # 内置函数
        builtin_names = self.registry.get_function_names_by_level(self.current_level)
        # 已批准的自定义函数
        approved_names = list(self._approved_functions.keys())
        return builtin_names + approved_names

    def get_function_summary(self) -> str:
        """
        生成当前可用函数的摘要，供Coding Agent使用

        Returns:
            格式化的函数摘要字符串
        """
        lines = []

        # 内置函数摘要
        lines.append(self.registry.get_summary_for_level(self.current_level))

        # 已批准的自定义函数
        if self._approved_functions:
            lines.append("\n## CUSTOM APPROVED FUNCTIONS")
            for func in self._approved_functions.values():
                params_str = ", ".join([
                    f"{p['name']}: {p['type']}"
                    for p in func.parameters
                ])
                lines.append(f"{func.function_name}({params_str}) -> {func.returns}")
                lines.append(f"    {func.description}")
                lines.append("")

        return "\n".join(lines)

    def check_capability(self, required_capability: str) -> Dict[str, Any]:
        """
        检查是否有能力完成指定的功能

        Args:
            required_capability: 需要的功能描述

        Returns:
            {
                "has_capability": bool,
                "matching_function": str | None,
                "similar_functions": List[str],
                "confidence": float
            }
        """
        available_names = self.get_available_function_names()

        # 精确匹配
        if required_capability in available_names:
            return {
                "has_capability": True,
                "matching_function": required_capability,
                "similar_functions": [],
                "confidence": 1.0
            }

        # 查找相似函数
        similar = self.registry.find_similar_functions(required_capability)
        similar_names = [f.name for f in similar if f.name in available_names]

        if similar_names:
            return {
                "has_capability": True,
                "matching_function": similar_names[0],
                "similar_functions": similar_names,
                "confidence": 0.7
            }

        return {
            "has_capability": False,
            "matching_function": None,
            "similar_functions": similar_names,
            "confidence": 0.0
        }

    def submit_new_function(self,
                            function_name: str,
                            function_code: str,
                            description: str,
                            parameters: List[Dict[str, Any]],
                            returns: str,
                            context: str) -> str:
        """
        提交新函数到审核队列

        Returns:
            pr_id: 生成的PR ID
        """
        pr_id = f"pr_{uuid.uuid4().hex[:8]}"

        pending = PendingFunction(
            pr_id=pr_id,
            function_name=function_name,
            function_code=function_code,
            description=description,
            parameters=parameters,
            returns=returns,
            context=context,
            submitted_at=datetime.now().isoformat(),
            status="pending_pr_review"
        )

        # 保存到pending目录
        pending_path = self.pending_dir / f"{pr_id}.json"
        with open(pending_path, 'w') as f:
            json.dump(asdict(pending), f, indent=2)

        return pr_id

    def get_pending_function(self, pr_id: str) -> Optional[PendingFunction]:
        """获取待审核函数"""
        pending_path = self.pending_dir / f"{pr_id}.json"
        if not pending_path.exists():
            return None

        with open(pending_path, 'r') as f:
            data = json.load(f)
        return PendingFunction(**data)

    def update_pending_function(self, pr_id: str, updates: Dict[str, Any]):
        """更新待审核函数状态"""
        pending = self.get_pending_function(pr_id)
        if not pending:
            raise ValueError(f"PR {pr_id} not found")

        pending_dict = asdict(pending)
        pending_dict.update(updates)

        pending_path = self.pending_dir / f"{pr_id}.json"
        with open(pending_path, 'w') as f:
            json.dump(pending_dict, f, indent=2)

    def add_to_human_review_queue(self, pr_id: str, pr_review_result: Dict[str, Any]):
        """将函数添加到人类审核队列"""
        # 更新pending状态
        self.update_pending_function(pr_id, {
            "status": "pending_human_review",
            "pr_review_result": pr_review_result
        })

        # 添加到review_queue
        queue_path = self.review_queue_dir / "pending_reviews.json"
        if queue_path.exists():
            with open(queue_path, 'r') as f:
                queue = json.load(f)
        else:
            queue = []

        pending = self.get_pending_function(pr_id)

        queue.append({
            "pr_id": pr_id,
            "function_name": pending.function_name,
            "description": pending.description,
            "context": pending.context,
            "pr_review_decision": pr_review_result.get("decision"),
            "pr_review_reason": pr_review_result.get("recommendation_reason"),
            "human_review_questions": pr_review_result.get("human_review_questions", []),
            "added_at": datetime.now().isoformat(),
            "human_decision": None,  # Human fills this: "approve" or "reject"
            "human_comment": None    # Human fills this
        })

        with open(queue_path, 'w') as f:
            json.dump(queue, f, indent=2)

    def check_human_reviews(self) -> List[Dict[str, Any]]:
        """
        检查人类审核队列中是否有已完成的审核

        Returns:
            已完成审核的PR列表
        """
        queue_path = self.review_queue_dir / "pending_reviews.json"
        if not queue_path.exists():
            return []

        with open(queue_path, 'r') as f:
            queue = json.load(f)

        completed = []
        remaining = []

        for item in queue:
            if item.get("human_decision"):
                completed.append(item)
            else:
                remaining.append(item)

        # 更新队列，移除已完成的
        if completed:
            with open(queue_path, 'w') as f:
                json.dump(remaining, f, indent=2)

            # 记录到历史
            self._add_to_review_history(completed)

        return completed

    def _add_to_review_history(self, reviews: List[Dict[str, Any]]):
        """记录审核历史"""
        history_path = self.review_queue_dir / "review_history.json"
        if history_path.exists():
            with open(history_path, 'r') as f:
                history = json.load(f)
        else:
            history = []

        for review in reviews:
            review["completed_at"] = datetime.now().isoformat()
            history.append(review)

        with open(history_path, 'w') as f:
            json.dump(history, f, indent=2)

    def approve_function(self, pr_id: str):
        """批准函数并添加到函数库"""
        pending = self.get_pending_function(pr_id)
        if not pending:
            raise ValueError(f"PR {pr_id} not found")

        # 创建ApprovedFunction
        approved = ApprovedFunction(
            function_name=pending.function_name,
            function_code=pending.function_code,
            description=pending.description,
            parameters=pending.parameters,
            returns=pending.returns,
            approved_at=datetime.now().isoformat(),
            pr_id=pr_id
        )

        # 保存函数代码文件
        code_path = self.approved_dir / f"{pending.function_name}.py"
        with open(code_path, 'w') as f:
            f.write(f'"""\n{pending.description}\n\nApproved from: {pr_id}\n"""\n\n')
            f.write(pending.function_code)

        # 添加到内存
        self._approved_functions[pending.function_name] = approved

        # 更新索引
        self._save_approved_index()

        # 更新pending状态
        self.update_pending_function(pr_id, {"status": "approved"})

        # 删除pending文件
        pending_path = self.pending_dir / f"{pr_id}.json"
        if pending_path.exists():
            pending_path.unlink()

    def reject_function(self, pr_id: str, reason: str):
        """拒绝函数"""
        self.update_pending_function(pr_id, {
            "status": "rejected",
            "human_comment": reason
        })

        # 可选：移动到rejected目录或直接删除
        # 这里选择保留在pending目录但更新状态

    def process_completed_reviews(self):
        """处理所有已完成的人类审核"""
        completed = self.check_human_reviews()

        for review in completed:
            pr_id = review["pr_id"]
            decision = review.get("human_decision")
            comment = review.get("human_comment", "")

            # 更新pending函数
            self.update_pending_function(pr_id, {
                "human_decision": decision,
                "human_comment": comment
            })

            if decision == "approve":
                self.approve_function(pr_id)
            elif decision == "reject":
                self.reject_function(pr_id, comment)

        return completed

    def get_library_status(self) -> Dict[str, Any]:
        """获取函数库状态"""
        builtin_functions = self.registry.get_functions_by_level(self.current_level)

        pending_files = list(self.pending_dir.glob("pr_*.json"))
        pending_count = len(pending_files)

        queue_path = self.review_queue_dir / "pending_reviews.json"
        if queue_path.exists():
            with open(queue_path, 'r') as f:
                human_queue = json.load(f)
            human_queue_count = len(human_queue)
        else:
            human_queue_count = 0

        return {
            "current_level": self.current_level.value,
            "builtin_function_count": len(builtin_functions),
            "approved_custom_count": len(self._approved_functions),
            "total_available": len(builtin_functions) + len(self._approved_functions),
            "pending_pr_review": pending_count - human_queue_count,
            "pending_human_review": human_queue_count,
            "builtin_functions": [f.name for f in builtin_functions],
            "approved_custom_functions": list(self._approved_functions.keys())
        }
