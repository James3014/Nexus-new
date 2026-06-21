import pytest
import scripts.benchmarks.deepswe_task4_singleton_race as m

def test_singleton_race():
    m.test_challenge()

# -------

import scripts.benchmarks.deepswe_task5_counter_race as m5

def test_counter_race():
    m5.test_challenge()

# -------

import scripts.benchmarks.deepswe_task6_cache_race as m6

def test_cache_race():
    m6.test_challenge()

# -------

import scripts.benchmarks.deepswe_task7_pubsub_race as m7

def test_pubsub_race():
    m7.test_challenge()

# -------

import scripts.benchmarks.deepswe_task8_transaction_race as m8

def test_transaction_race():
    m8.test_challenge()

# -------

import scripts.benchmarks.deepswe_task9_pool_race as m9

def test_pool_race():
    m9.test_challenge()

# -------

import scripts.benchmarks.deepswe_task10_ordered_list_race as m10

def test_ordered_list_race():
    m10.test_challenge()

# -------

import scripts.benchmarks.deepswe_task3_concurrency_race as m3

def test_concurrency_003_race():
    assert m3.test_challenge() is True

