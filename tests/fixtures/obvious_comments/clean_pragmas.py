#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# type: ignore
def untyped_func(a, b):
    return a + b


# noqa: E501
class VeryLongClass:
    pass


# pragma: no cover
def unreachable_code():
    raise NotImplementedError


# pylint: disable=invalid-name
def bad_name():
    pass


# fmt: off
x = 1


# isort: skip
import sys
