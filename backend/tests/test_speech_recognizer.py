from backend.utils.speech_recognizer import (
    SpeechRecognitionConfig,
    SpeechRecognitionMethod,
    SpeechRecognizer,
)


def test_sensevoice_word_timestamps_override_coarse_sentence_info():
    recognizer = SpeechRecognizer.__new__(SpeechRecognizer)
    words = list(
        "这是第一段字幕没有被三十秒粗粒度时间轴折叠。"
        "这里是第二段字幕，也应该使用词级时间戳。"
        "最后一段用于验证音频末尾。"
    )
    timestamps = [
        [1050 + index * 800, 1550 + index * 800]
        for index in range(len(words))
    ]
    full_text = "".join(words)
    result = [
        {
            "text": full_text,
            "words": words,
            "timestamp": timestamps,
            "sentence_info": [
                {"sentence": full_text[:32], "start": 0, "end": 30010},
                {"sentence": full_text[32:], "start": 30010, "end": 45080},
            ],
        }
    ]

    segments = recognizer._extract_sensevoice_segments(result, 45100)

    assert len(segments) > 2
    assert segments[0]["start"] == timestamps[0][0]
    assert segments[-1]["end"] == timestamps[-1][1]
    assert "".join(segment["text"].replace(" ", "") for segment in segments) == full_text
    assert all(segment["end"] - segment["start"] <= 8000 for segment in segments)
    assert all(
        current["start"] >= previous["end"]
        for previous, current in zip(segments, segments[1:])
    )
    assert segments[-1]["end"] <= 45100


def test_sensevoice_dict_timestamps_use_seconds_and_preserve_word_boundaries():
    recognizer = SpeechRecognizer.__new__(SpeechRecognizer)
    result = [
        {
            "text": "Hello, world. Next cue.",
            "timestamps": [
                {"token": "Hello", "start_time": 1.0, "end_time": 1.4},
                {"token": ",", "start_time": 1.4, "end_time": 1.5},
                {"token": "world", "start_time": 1.5, "end_time": 2.0},
                {"token": ".", "start_time": 2.0, "end_time": 2.2},
                {"token": "Next", "start_time": 2.5, "end_time": 2.9},
                {"token": "cue", "start_time": 3.0, "end_time": 3.4},
                {"token": ".", "start_time": 3.4, "end_time": 3.5},
            ],
            "sentence_info": [
                {"sentence": "Hello, world. Next cue.", "start": 0, "end": 4000}
            ],
        }
    ]

    segments = recognizer._extract_sensevoice_segments(result, 4000)

    assert segments == [
        {"start": 1000, "end": 2200, "text": "Hello, world."},
        {"start": 2500, "end": 3500, "text": "Next cue."},
    ]


def test_sensevoice_misaligned_words_fall_back_without_dropping_text():
    recognizer = SpeechRecognizer.__new__(SpeechRecognizer)
    result = [
        {
            "text": "完整字幕",
            "words": ["不", "完整"],
            "timestamp": [[100, 200]],
            "sentence_info": [
                {"sentence": "完整字幕", "start": 0, "end": 2500}
            ],
        }
    ]

    segments = recognizer._extract_sensevoice_segments(result, 2500)

    assert segments == [{"start": 0, "end": 2500, "text": "完整字幕"}]


def test_sensevoice_words_reuse_source_text_boundaries_for_numbers():
    recognizer = SpeechRecognizer.__new__(SpeechRecognizer)
    words = ["It", "was", "the", "mid", "1", "9", "century", "."]
    result = [
        {
            "text": "It was the mid 19 century.",
            "words": words,
            "timestamp": [
                [100 + index * 400, 400 + index * 400]
                for index in range(len(words))
            ],
        }
    ]

    segments = recognizer._extract_sensevoice_segments(result, 4000)

    assert segments == [
        {"start": 100, "end": 3200, "text": "It was the mid 19 century."}
    ]


def test_sensevoice_generation_explicitly_requests_output_timestamps(tmp_path):
    recognizer = SpeechRecognizer.__new__(SpeechRecognizer)
    recognizer.available_methods = {SpeechRecognitionMethod.SENSEVOICE: True}
    video_path = tmp_path / "input.mp4"
    audio_path = tmp_path / "input.wav"
    output_path = tmp_path / "output.srt"
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    captured_kwargs = {}

    class StubModel:
        def generate(self, **kwargs):
            captured_kwargs.update(kwargs)
            return [
                {
                    "text": "test.",
                    "words": ["test", "."],
                    "timestamp": [[100, 900], [900, 1000]],
                }
            ]

    recognizer._extract_audio_from_video = lambda *_: audio_path
    recognizer._resolve_asr_device = lambda: "cpu"
    recognizer._get_sensevoice_model = lambda *_: StubModel()
    recognizer._get_audio_duration_ms = lambda *_: 2000
    config = SpeechRecognitionConfig(
        method=SpeechRecognitionMethod.SENSEVOICE,
        model="iic/SenseVoiceSmall",
    )

    recognizer._generate_subtitle_sensevoice(video_path, output_path, config)

    assert captured_kwargs["output_timestamp"] is True
    assert output_path.exists()
