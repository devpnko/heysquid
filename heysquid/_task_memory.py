"""
heysquid._task_memory — task index & memory (tasks/ directory).

Functions:
- load_index, save_index, update_index
- search_memory, get_task_dir, load_memory
"""

import os
import json
from datetime import datetime

from .paths import INDEX_FILE, TASKS_DIR
from .config import TASKS_DIR_STR


def load_index():
    """인덱스 파일 로드"""
    if not os.path.exists(INDEX_FILE):
        return {"tasks": [], "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] index.json 읽기 오류: {e}")
        return {"tasks": [], "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def save_index(index_data):
    """인덱스 파일 저장"""
    os.makedirs(TASKS_DIR_STR, exist_ok=True)
    index_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def update_index(message_id, instruction, result_summary="", files=None, chat_id=None, timestamp=None):
    """인덱스 업데이트"""
    index = load_index()

    keywords = []
    for word in instruction.split():
        if len(word) >= 2:
            keywords.append(word)
    keywords = list(set(keywords))[:10]

    existing_task = None
    for task in index["tasks"]:
        if task["message_id"] == message_id:
            existing_task = task
            break

    task_data = {
        "message_id": message_id,
        "timestamp": timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "instruction": instruction,
        "keywords": keywords,
        "result_summary": result_summary,
        "files": files or [],
        "chat_id": chat_id,
        "task_dir": os.path.join(TASKS_DIR_STR, f"msg_{message_id}")
    }

    if existing_task:
        existing_task.update(task_data)
    else:
        index["tasks"].append(task_data)

    index["tasks"].sort(key=lambda x: x["message_id"], reverse=True)
    save_index(index)
    print(f"[INDEX] 인덱스 업데이트: message_id={message_id}")


def search_memory(keyword=None, message_id=None):
    """인덱스에서 작업 검색"""
    index = load_index()

    if message_id is not None:
        for task in index["tasks"]:
            if task["message_id"] == message_id:
                return [task]
        return []

    if keyword:
        matches = []
        keyword_lower = keyword.lower()
        for task in index["tasks"]:
            if (keyword_lower in task["instruction"].lower() or
                any(keyword_lower in kw.lower() for kw in task["keywords"])):
                matches.append(task)
        return matches

    return index["tasks"]


def get_task_dir(message_id):
    """메시지 ID 기반 작업 폴더 경로 반환"""
    task_dir = os.path.join(TASKS_DIR_STR, f"msg_{message_id}")
    if not os.path.exists(task_dir):
        os.makedirs(task_dir)
        print(f"[DIR] 작업 폴더 생성: {task_dir}")
    return task_dir


def load_memory():
    """기존 메모리 파일 전부 읽기 (tasks/*/task_info.txt)"""
    if not os.path.exists(TASKS_DIR_STR):
        return []

    memories = []

    for task_folder in os.listdir(TASKS_DIR_STR):
        if task_folder.startswith("msg_"):
            task_dir = os.path.join(TASKS_DIR_STR, task_folder)
            task_info_file = os.path.join(task_dir, "task_info.txt")

            if os.path.exists(task_info_file):
                try:
                    message_id = int(task_folder.split("_")[1])
                    with open(task_info_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        memories.append({
                            "message_id": message_id,
                            "task_dir": task_dir,
                            "content": content
                        })
                except Exception as e:
                    print(f"[WARN] {task_folder}/task_info.txt 읽기 오류: {e}")

    memories.sort(key=lambda x: x["message_id"], reverse=True)
    return memories
