#!/bin/python3

'''Finds an optimal settlement from a list of cashouts.'''
import collections
import csv
import functools
import math
import multiprocessing
import os
import random
import sys

random.seed(123)

detailed_links_players = ['@felipeal']

def read_cashouts(filename):
    '''Read (player, cashout) pairs from an input CSV file.

    Required columns:
        'Balance' -- cashout
        'Venmo'   -- player ID
    '''
    players = collections.defaultdict(int)

    with open(filename, newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        headers = next(reader)
        for row in reader:
            mapped_row = dict(zip(headers, row))
            try:
                cashout = int(mapped_row['Balance'].replace('.', ''))
            except ValueError:
                continue
            players[mapped_row['Venmo']] += cashout

    return list(players.items())


def edge_weight():
    '''Generate a weight for a payment graph edge.'''
    return random.randint(-1_000_000_000, 1_000_000_000)


def find_settlement_or(cashouts, _):
    '''Finds a feasible settlement in a payment graph using OR-tools library.'''
    from ortools.graph import pywrapgraph
    min_cost_flow = pywrapgraph.SimpleMinCostFlow()

    for player_from, cashout1 in enumerate(cashouts):
        if cashout1 <= 0:
            continue
        for player_to, cashout2 in enumerate(cashouts):
            if cashout2 >= 0:
                continue
            cap = min(cashout1, -cashout2)
            min_cost_flow.AddArcWithCapacityAndUnitCost(
                player_from, player_to, cap, edge_weight())

    for player_id, cashout in enumerate(cashouts):
        min_cost_flow.SetNodeSupply(player_id, cashout)

    status = min_cost_flow.Solve()
    assert status == min_cost_flow.OPTIMAL, status

    settlements = collections.defaultdict(list)
    for i in range(min_cost_flow.NumArcs()):
        if min_cost_flow.Flow(i) <= 0:
            continue
        settlements[min_cost_flow.Tail(i)].append(
            (min_cost_flow.Head(i), min_cost_flow.Flow(i)))

    return settlements


def find_settlement_nx(cashouts, _):
    '''Finds a feasible settlement in a payment graph using networkx library.'''
    import networkx as nx
    graph = nx.DiGraph()

    source, sink = len(cashouts), len(cashouts) + 1
    for player, cashout in enumerate(cashouts):
        if cashout < 0:
            graph.add_edge(source, player, capacity=-cashout)
        elif cashout > 0:
            graph.add_edge(player, sink, capacity=cashout)

    for player_from, cashout1 in enumerate(cashouts):
        if cashout1 >= 0:
            continue
        for player_to, cashout2 in enumerate(cashouts):
            if cashout2 <= 0:
                continue
            cap = min(-cashout1, cashout2)
            graph.add_edge(player_from, player_to, capacity=cap, weight=edge_weight())

    min_cost_flow = nx.max_flow_min_cost(graph, source, sink)

    settlements = collections.defaultdict(list)
    for player_from, cashout in enumerate(cashouts):
        if cashout >= 0:
            continue
        for player_to, payment in min_cost_flow[player_from].items():
            if payment <= 0:
                continue
            settlements[player_to].append((player_from, payment))

    return settlements


def find_best_settlement(settlement_finder, cashouts, num_trials):
    '''Finds a settlement with a minimum number of payments.'''
    best_cost, best_settlement = len(cashouts) * len(cashouts) + 1, None

    find_settlement = functools.partial(settlement_finder, cashouts)

    chunk = math.ceil(num_trials / multiprocessing.cpu_count())
    with multiprocessing.Pool() as pool:
        for settlement in pool.imap_unordered(find_settlement, range(num_trials), chunksize=chunk):
            cost = sum(len(al) for _, al in settlement.items())
            if cost < best_cost:
                best_cost, best_settlement = cost, settlement

    return best_settlement


def get_printable_dollar_amount(num):
    '''Gets a printable_dollar amount.'''
    quot, rem = divmod(num, 100)
    return f'${quot}.{rem:02}'

def get_venmo_profile_link(username):
    '''Gets a hyperlink to a Venmo profile. Username starts with @'''
    return '<a href="https://venmo.com/u/' + username[1:] + '">' + username + '</a>'

def get_venmo_amount_only_link(username, amount, description=None):
    '''Gets a hyperlink to a Venmo request. Username starts with @'''
    quot, rem = divmod(amount, 100)
    note = ''
    if description:
        note = '&note=' + description
    return f'<a href="https://venmo.com/?txn=charge&audience=private&recipients={username[1:]}&amount={quot}.{rem:02}{note}">' + get_printable_dollar_amount(amount) + '<a>'

# felipeal: merge both
def get_venmo_amount_and_username_link(username, amount, description=None):
    '''Gets a hyperlink to a Venmo request. Username starts with @'''
    quot, rem = divmod(amount, 100)
    note = ''
    if description:
        note = '&note=' + description
        printable_amount = get_printable_dollar_amount(amount);
    return f'{printable_amount} <a href="https://venmo.com/?txn=charge&audience=private&recipients={username[1:]}&amount={quot}.{rem:02}{note}">{username}<a>'


def print_settlement(settlement, description, players):
    '''Prints a settlement.'''
    # Not the case anymore (unless requestor's on detailed_links_players
#    print('<i>Click on <b>amount to request directly</b>; click on @username for Venmo profile</i><br>')
    print('<pre>')
    for player_id in sorted(settlement, key=lambda player_id: players[player_id][0].lower()):
        name, cashout = players[player_id]
        print(f'{get_venmo_profile_link(name)} requests {get_printable_dollar_amount(cashout)} from:')
        for payer in sorted(settlement[player_id], key=lambda p: (-p[1], players[p[0]][0].lower())):
            amount = payer[1]
            payer_username = players[payer[0]][0]
            if name in detailed_links_players:
                # 2 links: amount and profile
                print(
                    f'\t{get_venmo_amount_only_link(payer_username, amount, description)} {get_venmo_profile_link(payer_username)}')
            else:
                # 1 link with amount and username
                print(
                    f'\t{get_venmo_amount_and_username_link(payer_username, amount, description)}')
        print()
    print('</pre>')

def parse_args():
   ''' Parses the command-line arguments and return a tuple with filename, description, and number of trials'''
   import argparse
   parser = argparse.ArgumentParser()
   parser.add_argument('-f', '--file', required=True, help='Path to .csv file with game info')
   parser.add_argument('-d', '--desc', required=False, help='Venmo transaction descrption (defaults to ♥ when not set)', default='♥')
   parser.add_argument('-t', '--trials', required=False, help='Number of trials', default=1_001);

   args = parser.parse_args()

   return args.file, args.desc, args.trials

def main():
    '''Prints an optimal settlement for a list of cashouts provided in a CSV file.'''
    
    filename, description, num_trials = parse_args()
   
    try:
        import ortools.graph
        settlement_finder = find_settlement_or
    except ModuleNotFoundError:
        settlement_finder = find_settlement_nx

    player_cashouts = read_cashouts(filename)
    print ("best_settlement", player_cashouts)
    cashouts = [pc[1] for pc in player_cashouts]
    settlement = find_best_settlement(settlement_finder, cashouts, num_trials)
    print_settlement(settlement, description, player_cashouts)


if __name__ == '__main__':
    main()
