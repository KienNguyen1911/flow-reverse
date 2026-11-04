import pytest
from src.Bridge.flow.composer import (
    MentionSegment,
    TextSegment,
    parse_prompt_segments,
)


def test_parse_prompt_segments_image_numbers():
    refs = [
        {"alias_name": "model_a1b2c3", "media_id": "uuid-1"},
        {"alias_name": "garment_d4e5f6", "media_id": "uuid-2"},
        {"alias_name": "scene_789abc", "media_id": "uuid-3"},
    ]
    prompt = "Try-on photo of Image 1 wearing Image 2 in Image 3"
    segments = parse_prompt_segments(prompt, refs)

    assert len(segments) == 6
    assert segments[0] == TextSegment("Try-on photo of ")
    assert segments[1] == MentionSegment("model_a1b2c3", "uuid-1")
    assert segments[2] == TextSegment(" wearing ")
    assert segments[3] == MentionSegment("garment_d4e5f6", "uuid-2")
    assert segments[4] == TextSegment(" in ")
    assert segments[5] == MentionSegment("scene_789abc", "uuid-3")


def test_parse_prompt_segments_template_tags():
    refs = [
        {"alias_name": "model_111", "media_id": "m1"},
        {"alias_name": "garment_222", "media_id": "m2"},
    ]
    prompt = "A shot of {{@model}} wearing {{@garment}}"
    segments = parse_prompt_segments(prompt, refs)

    assert len(segments) == 4
    assert segments[0] == TextSegment("A shot of ")
    assert segments[1] == MentionSegment("model_111", "m1")
    assert segments[2] == TextSegment(" wearing ")
    assert segments[3] == MentionSegment("garment_222", "m2")


def test_parse_prompt_segments_at_mention_syntax():
    refs = [
        {"alias_name": "model_111", "media_id": "m1"},
        {"alias_name": "garment_222", "media_id": "m2"},
    ]
    prompt = "Fashion photo: @model with @garment."
    segments = parse_prompt_segments(prompt, refs)

    assert segments[0] == TextSegment("Fashion photo: ")
    assert segments[1] == MentionSegment("model_111", "m1")
    assert segments[2] == TextSegment(" with ")
    assert segments[3] == MentionSegment("garment_222", "m2")
    assert segments[4] == TextSegment(".")


def test_parse_prompt_segments_prepends_unmentioned_refs():
    refs = [
        {"alias_name": "model_111", "media_id": "m1"},
        {"alias_name": "garment_222", "media_id": "m2"},
    ]
    # Prompt only mentions Image 1, Image 2 is unmentioned
    prompt = "Close-up portrait of Image 1 smiling"
    segments = parse_prompt_segments(prompt, refs)

    # refs[1] should be prepended
    assert segments[0] == MentionSegment("garment_222", "m2")
    assert segments[1] == TextSegment(" Close-up portrait of ")
    assert segments[2] == MentionSegment("model_111", "m1")
    assert segments[3] == TextSegment(" smiling")


def test_parse_prompt_segments_prepends_all_when_no_mention():
    refs = [
        {"alias_name": "model_111", "media_id": "m1"},
        {"alias_name": "garment_222", "media_id": "m2"},
    ]
    prompt = "a girl walking down the street"
    segments = parse_prompt_segments(prompt, refs)

    assert segments[0] == MentionSegment("model_111", "m1")
    assert segments[1] == TextSegment(" ")
    assert segments[2] == MentionSegment("garment_222", "m2")
    assert segments[3] == TextSegment(" a girl walking down the street")


def test_parse_prompt_segments_empty_prompt():
    refs = [{"alias_name": "model_111", "media_id": "m1"}]
    segments = parse_prompt_segments("", refs)

    assert len(segments) == 1
    assert segments[0] == MentionSegment("model_111", "m1")


def test_parse_prompt_segments_no_refs():
    segments = parse_prompt_segments("simple text prompt", [])
    assert len(segments) == 1
    assert segments[0] == TextSegment("simple text prompt")
