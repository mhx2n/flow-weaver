"""Ordered code sections of প্রবাহ bot.

Each ``NN_<slug>.py`` file is a raw chunk of the original single-file
bot. They are NOT meant to be imported individually — the runner in
``bot/__main__.py`` ``exec``s them into one shared globals dict in
filename order, exactly reproducing the original execution order
(including the late-loaded "FINAL OVERRIDE / PATCH" sections that
monkey-patch earlier definitions).
"""