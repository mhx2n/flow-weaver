#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
প্রবাহ — Professional Ultra Quiz Bot (Single File)

Core features preserved:
- Admin/Owner can send Text blocks or Polls/Quizzes -> parsed -> buffered
- /done exports CSV (utf-8-sig) then clears buffer
- /filter adds per-admin filters
- /clear clears buffer

Enhanced (new additions, without breaking existing behavior):
- Professional English UI + role-based /help (polished)
- Reply-aware commands:
  - /ask, /reply, /broadcast work either inline OR by replying to a message
- Channel privacy / access control:
  - Owner sees all channels
  - Admin sees ONLY channels they added
  - Owner can grant/revoke “view all channels” access to selected admins
- Per-admin visibility (owner can view all):
  - /adminpanel: admins see own stats; owner sees all
  - /banned: admins see only bans they issued; owner sees all
"""

import asyncio
import contextlib
import datetime as dt
import json
import logging
from multiprocessing import context
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import os
import re
import sqlite3
import sys
import tempfile
import time
import uuid
from bs4 import BeautifulSoup
from datetime import datetime
import base64
import html as html_escape
import requests
from concurrent.futures import ThreadPoolExecutor
#from openai import OpenAI
import importlib.util
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Iterable
#from openai import OpenAI
import pandas as pd
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.error import RetryAfter, Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ApplicationHandlerStop,
)

