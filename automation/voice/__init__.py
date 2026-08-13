"""Voice mode — local speech in, spoken answers out.

The mic is click-gated in the dashboard and every speech segment is transcribed
locally, so the wake phrase is a text check on the transcript rather than a
second always-listening model. See ``wake``, ``intents`` and ``speech_form``.
"""
