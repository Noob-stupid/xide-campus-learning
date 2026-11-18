# -*- coding: utf-8 -*-
"""测试环境默认禁用真实大模型调用，避免联网与超时。"""
import os

os.environ.setdefault('ZX_DISABLE_LLM', '1')