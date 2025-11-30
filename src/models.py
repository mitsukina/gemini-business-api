from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel
from dataclasses import dataclass, field

class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatRequest(BaseModel):
    model: str = "gemini-auto"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    user: Optional[str] = None

@dataclass
class ChatImage:
    url: str
    filename: str
    mime_type: str
    size: int
    chat_id: str
    image_index: int = 1