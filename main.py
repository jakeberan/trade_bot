import streamlit as st
import requests
import pandas as pd
from itertools import combinations
import time

# Constants
SLEEPER_USERNAME = "beran2"
FAIR_TRADE_THRESHOLD = 0.15  # 15% value difference

st.set_page_config(page_title="Fantasy Trade Generator", layout="wide")

# Caching functions
@st.cache_data(ttl=3600)
def get_sleeper_user(username):
    """Get Sleeper user ID from username"""
    url = f"https://api.sleeper.app/v1/user/{username}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

@st.cache_data(ttl=3600)
def get_league_info(league_id):
    """Get league information"""
    url = f"https://api.sleeper.app/v1/league/{league_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

@st.cache_data(ttl=3600)
def get_league_rosters(league_id):
    """Get all rosters in the league"""
    url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

@st.cache_data(ttl=3600)
def get_league_users(league_id):
    """Get all users in the league"""
    url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

@st.cache_data(ttl=3600)
def get_player_values(league_type):
    """Get player values from FantasyCalc"""
    if league_type == "Dynasty":
        url = "https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1"
    else:  # Redraft
        url = "https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1&numTeams=12&ppr=1"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return {player['player']['sleeperId']: player['value'] for player in data if player['player'].get('sleeperId')}
    return {}

@st.cache_data(ttl=3600)
def get_all_players():
    """Get all NFL players from Sleeper"""
    url = "https://api.sleeper.app/v1/players/nfl"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return {}

def calculate_trade_value(players_given, players_received, player_values):
    """Calculate total value for both sides of trade"""
    given_value = sum([player_values.get(p, 0) for p in players_given])
    received_value = sum([player_values.get(p, 0) for p in players_received])
    return given_value, received_value

def is_fair_trade(given_value, received_value):
    """Check if trade is within fair threshold"""
    if given_value == 0 or received_value == 0:
        return False
    ratio = max(given_value, received_value) / min(given_value, received_value)
    return ratio <= (1 + FAIR_TRADE_THRESHOLD)

def generate_target_player_trades(target_player_id, my_roster, opponent_roster, player_values, all_players, max_players=3):
    """Generate trades to acquire a specific target player"""
    trades = []
    
    if target_player_id not in opponent_roster:
        return trades
    
    target_value = player_values.get(target_player_id, 0)
    if target_value == 0:
        return trades
    
    # Try combinations of my players to match target value
    for r in range(1, min(max_players + 1, len(my_roster) + 1)):
        for combo in combinations(my_roster, r):
            given_value, received_value = calculate_trade_value(list(combo), [target_player_id], player_values)
            
            if is_fair_trade(given_value, received_value):
                trades.append({
                    'you_give': [all_players.get(p, {}).get('full_name', p) for p in combo],
                    'you_receive': [all_players.get(target_player_id, {}).get('full_name', target_player_id)],
                    'you_give_ids': list(combo),
                    'you_receive_ids': [target_player_id],
                    'you_give_value': given_value,
                    'you_receive_value': received_value,
                    'net_value': received_value - given_value
                })
    
    return trades

def generate_value_improvement_trades(my_roster, opponent_roster, player_values, all_players, max_players=3):
    """Generate trades that improve your team's value"""
    trades = []
    
    # Try combinations where you gain value
    for my_r in range(1, min(max_players + 1, len(my_roster) + 1)):
        for opp_r in range(1, min(max_players + 1, len(opponent_roster) + 1)):
            for my_combo in combinations(my_roster, my_r):
                for opp_combo in combinations(opponent_roster, opp_r):
                    given_value, received_value = calculate_trade_value(list(my_combo), list(opp_combo), player_values)
                    
                    # Only include if you gain value and it's fair
                    if received_value > given_value and is_fair_trade(given_value, received_value):
                        trades.append({
                            'you_give': [all_players.get(p, {}).get('full_name', p) for p in my_combo],
                            'you_receive': [all_players.get(p, {}).get('full_name', p) for p in opp_combo],
                            'you_give_ids': list(my_combo),
                            'you_receive_ids': list(opp_combo),
                            'you_give_value': given_value,
                            'you_receive_value': received_value,
                            'net_value': received_value - given_value
                        })
    
    # Sort by net value gained
    trades.sort(key=lambda x: x['net_value'], reverse=True)
    return trades[:20]  # Return top 20

def generate_buy_low_trades(my_roster, opponent_roster, player_values, all_players, max_players=2):
    """Find trades where you can buy low on undervalued players"""
    # This is similar to value improvement but focuses on getting higher value players
    trades = generate_value_improvement_trades(my_roster, opponent_roster, player_values, all_players, max_players)
    
    # Filter to only trades where we're getting fewer but more valuable players
    buy_low_trades = [t for t in trades if len(t['you_receive_ids']) <= len(t['you_give_ids'])]
    
    return buy_low_trades[:15]

def generate_custom_trades(selected_give, selected_receive, my_roster, all_rosters, player_values, all_players):
    """Generate fair trades for manually selected players"""
    trades = []
    
    if not selected_receive:
        return trades
    
    # Calculate current value
    given_value = sum([player_values.get(p, 0) for p in selected_give])
    received_value = sum([player_values.get(p, 0) for p in selected_receive])
    
    # Find teams that have the desired players
    for roster in all_rosters:
        opponent_roster = roster.get('players', [])
        if all(p in opponent_roster for p in selected_receive):
            # Check if fair with current selection
            if is_fair_trade(given_value, received_value):
                trades.append({
                    'team_id': roster['roster_id'],
                    'you_give': [all_players.get(p, {}).get('full_name', p) for p in selected_give],
                    'you_receive': [all_players.get(p, {}).get('full_name', p) for p in selected_receive],
                    'you_give_ids': selected_give,
                    'you_receive_ids': selected_receive,
                    'you_give_value': given_value,
                    'you_receive_value': received_value,
                    'net_value': received_value - given_value
                })
            else:
                # Try to balance the trade
                value_diff = received_value - given_value
                if value_diff > 0:  # You need to give more
                    for player in my_roster:
                        if player not in selected_give:
                            new_given = selected_give + [player]
                            new_given_value = sum([player_values.get(p, 0) for p in new_given])
                            if is_fair_trade(new_given_value, received_value):
                                trades.append({
                                    'team_id': roster['roster_id'],
                                    'you_give': [all_players.get(p, {}).get('full_name', p) for p in new_given],
                                    'you_receive': [all_players.get(p, {}).get('full_name', p) for p in selected_receive],
                                    'you_give_ids': new_given,
                                    'you_receive_ids': selected_receive,
                                    'you_give_value': new_given_value,
                                    'you_receive_value': received_value,
                                    'net_value': received_value - new_given_value,
                                    'balanced': True
                                })
    
    return trades

# Main App
st.title("🏈 Fantasy Football Trade Generator")
st.markdown(f"*Logged in as: {SLEEPER_USERNAME}*")

# Sidebar inputs
with st.sidebar:
    st.header("League Settings")
    league_id = st.text_input("League ID", placeholder="Enter your Sleeper league ID")
    league_type = st.selectbox("League Type", ["Dynasty", "Redraft"])
    
    st.markdown("---")
    st.markdown("### Trade Fairness")
    st.info(f"Trades within **{int(FAIR_TRADE_THRESHOLD*100)}%** value difference are considered fair")

if not league_id:
    st.info("👈 Enter your Sleeper League ID in the sidebar to get started!")
    st.markdown("### How to find your League ID:")
    st.markdown("1. Go to your league on Sleeper.app")
    st.markdown("2. Look at the URL - it will be like `sleeper.app/leagues/LEAGUE_ID/team`")
    st.markdown("3. Copy the numbers after `/leagues/`")
    st.stop()

# Load data
with st.spinner("Loading league data..."):
    user_data = get_sleeper_user(SLEEPER_USERNAME)
    league_info = get_league_info(league_id)
    rosters = get_league_rosters(league_id)
    users = get_league_users(league_id)
    player_values = get_player_values(league_type)
    all_players = get_all_players()

if not all([user_data, league_info, rosters, users]):
    st.error("❌ Could not load league data. Please check your League ID.")
    st.stop()

# Find user's roster
user_id = user_data['user_id']
my_roster_data = next((r for r in rosters if r['owner_id'] == user_id), None)

if not my_roster_data:
    st.error("❌ Could not find your roster in this league.")
    st.stop()

my_roster = my_roster_data.get('players', [])
my_roster_id = my_roster_data['roster_id']

# Create user mapping
user_map = {u['user_id']: u['display_name'] for u in users}
roster_to_user = {r['roster_id']: user_map.get(r['owner_id'], 'Unknown') for r in rosters}

# Display league info
st.success(f"✅ Loaded **{league_info['name']}** ({league_type})")
st.markdown(f"**Your Team:** {roster_to_user[my_roster_id]} | **Roster Size:** {len(my_roster)} players")

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs(["🎯 Target Player", "📈 Value Improvement", "💎 Buy Low", "🔧 Custom Trade"])

with tab1:
    st.header("Target a Specific Player")
    st.markdown("Find fair trades to acquire a player you want")
    
    # Get all players from other rosters
    other_rosters = [r for r in rosters if r['roster_id'] != my_roster_id]
    all_other_players = []
    for roster in other_rosters:
        for player_id in roster.get('players', []):
            if player_id in all_players:
                all_other_players.append({
                    'id': player_id,
                    'name': all_players[player_id].get('full_name', player_id),
                    'position': all_players[player_id].get('position', 'N/A'),
                    'team': all_players[player_id].get('team', 'FA'),
                    'value': player_values.get(player_id, 0),
                    'owner': roster_to_user[roster['roster_id']]
                })
    
    # Sort by value
    all_other_players.sort(key=lambda x: x['value'], reverse=True)
    
    if all_other_players:
        selected_target = st.selectbox(
            "Select Target Player",
            options=all_other_players,
            format_func=lambda x: f"{x['name']} ({x['position']}, {x['team']}) - Value: {x['value']:.0f} - Owner: {x['owner']}"
        )
        
        if st.button("Generate Trades", key="target_btn"):
            with st.spinner("Analyzing possible trades..."):
                # Find opponent roster
                opponent_roster_data = next((r for r in other_rosters if selected_target['owner'] == roster_to_user[r['roster_id']]), None)
                if opponent_roster_data:
                    opponent_roster = opponent_roster_data.get('players', [])
                    trades = generate_target_player_trades(
                        selected_target['id'],
                        my_roster,
                        opponent_roster,
                        player_values,
                        all_players
                    )
                    
                    if trades:
                        st.success(f"Found {len(trades)} possible trades!")
                        for i, trade in enumerate(trades[:10], 1):
                            with st.expander(f"Trade Option {i} (Net: {trade['net_value']:+.0f})"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.markdown("**You Give:**")
                                    for player in trade['you_give']:
                                        st.markdown(f"- {player}")
                                    st.markdown(f"*Total Value: {trade['you_give_value']:.0f}*")
                                with col2:
                                    st.markdown("**You Receive:**")
                                    for player in trade['you_receive']:
                                        st.markdown(f"- {player}")
                                    st.markdown(f"*Total Value: {trade['you_receive_value']:.0f}*")
                    else:
                        st.warning("No fair trades found for this player.")

with tab2:
    st.header("Value Improvement Trades")
    st.markdown("Find trades where you gain value while staying fair")
    
    opponent_select = st.selectbox(
        "Select Opponent",
        options=[roster_to_user[r['roster_id']] for r in other_rosters],
        key="value_opponent"
    )
    
    if st.button("Find Trades", key="value_btn"):
        with st.spinner("Finding value trades..."):
            # Get opponent roster
            opponent_roster_data = next((r for r in rosters if roster_to_user[r['roster_id']] == opponent_select), None)
            if opponent_roster_data:
                opponent_roster = opponent_roster_data.get('players', [])
                trades = generate_value_improvement_trades(my_roster, opponent_roster, player_values, all_players)
                
                if trades:
                    st.success(f"Found {len(trades)} trades that improve your value!")
                    for i, trade in enumerate(trades, 1):
                        with st.expander(f"Trade {i} - Gain {trade['net_value']:.0f} value"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**You Give:**")
                                for player in trade['you_give']:
                                    st.markdown(f"- {player}")
                                st.markdown(f"*Total Value: {trade['you_give_value']:.0f}*")
                            with col2:
                                st.markdown("**You Receive:**")
                                for player in trade['you_receive']:
                                    st.markdown(f"- {player}")
                                st.markdown(f"*Total Value: {trade['you_receive_value']:.0f}*")
                else:
                    st.warning("No value-improving trades found with this team.")

with tab3:
    st.header("Buy Low Opportunities")
    st.markdown("Find trades where you consolidate players to get stars")
    
    opponent_select_bl = st.selectbox(
        "Select Opponent",
        options=[roster_to_user[r['roster_id']] for r in other_rosters],
        key="buylow_opponent"
    )
    
    if st.button("Find Buy Low Trades", key="buylow_btn"):
        with st.spinner("Finding buy low opportunities..."):
            opponent_roster_data = next((r for r in rosters if roster_to_user[r['roster_id']] == opponent_select_bl), None)
            if opponent_roster_data:
                opponent_roster = opponent_roster_data.get('players', [])
                trades = generate_buy_low_trades(my_roster, opponent_roster, player_values, all_players)
                
                if trades:
                    st.success(f"Found {len(trades)} buy low opportunities!")
                    for i, trade in enumerate(trades, 1):
                        with st.expander(f"Trade {i} - Net Value: {trade['net_value']:+.0f}"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**You Give:**")
                                for player in trade['you_give']:
                                    st.markdown(f"- {player}")
                                st.markdown(f"*Total Value: {trade['you_give_value']:.0f}*")
                            with col2:
                                st.markdown("**You Receive:**")
                                for player in trade['you_receive']:
                                    st.markdown(f"- {player}")
                                st.markdown(f"*Total Value: {trade['you_receive_value']:.0f}*")
                else:
                    st.warning("No buy low trades found with this team.")

with tab4:
    st.header("Custom Trade Builder")
    st.markdown("Manually select players and find fair trade partners")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Your Players to Trade")
        my_players_list = [{'id': p, 'name': all_players.get(p, {}).get('full_name', p), 
                           'value': player_values.get(p, 0)} for p in my_roster]
        my_players_list.sort(key=lambda x: x['value'], reverse=True)
        
        selected_give = st.multiselect(
            "Select players you'll give up",
            options=[p['id'] for p in my_players_list],
            format_func=lambda x: f"{next(p['name'] for p in my_players_list if p['id'] == x)} (Value: {player_values.get(x, 0):.0f})"
        )
    
    with col2:
        st.subheader("Players to Acquire")
        target_players_list = []
        for roster in other_rosters:
            for player_id in roster.get('players', []):
                if player_id in all_players:
                    target_players_list.append({
                        'id': player_id,
                        'name': all_players[player_id].get('full_name', player_id),
                        'value': player_values.get(player_id, 0)
                    })
        target_players_list.sort(key=lambda x: x['value'], reverse=True)
        
        selected_receive = st.multiselect(
            "Select players you want to receive",
            options=[p['id'] for p in target_players_list],
            format_func=lambda x: f"{next(p['name'] for p in target_players_list if p['id'] == x)} (Value: {player_values.get(x, 0):.0f})"
        )
    
    if selected_give or selected_receive:
        give_value = sum([player_values.get(p, 0) for p in selected_give])
        receive_value = sum([player_values.get(p, 0) for p in selected_receive])
        
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Your Side Value", f"{give_value:.0f}")
        with col_b:
            st.metric("Their Side Value", f"{receive_value:.0f}")
        with col_c:
            diff = receive_value - give_value
            st.metric("Net Value", f"{diff:+.0f}", delta_color="normal")
        
        if give_value > 0 and receive_value > 0:
            if is_fair_trade(give_value, receive_value):
                st.success("✅ This trade is within fair range!")
            else:
                st.warning("⚠️ This trade is outside the 15% fair range. Consider adjusting.")
    
    if st.button("Find Trade Partners", key="custom_btn"):
        if selected_receive:
            with st.spinner("Finding teams with these players..."):
                trades = generate_custom_trades(selected_give, selected_receive, my_roster, rosters, player_values, all_players)
                
                if trades:
                    st.success(f"Found {len(trades)} possible trade partner(s)!")
                    for trade in trades:
                        team_name = roster_to_user[trade['team_id']]
                        balanced = trade.get('balanced', False)
                        title = f"Trade with {team_name}" + (" (Balanced)" if balanced else "")
                        
                        with st.expander(title):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**You Give:**")
                                for player in trade['you_give']:
                                    st.markdown(f"- {player}")
                                st.markdown(f"*Total Value: {trade['you_give_value']:.0f}*")
                            with col2:
                                st.markdown("**You Receive:**")
                                for player in trade['you_receive']:
                                    st.markdown(f"- {player}")
                                st.markdown(f"*Total Value: {trade['you_receive_value']:.0f}*")
                            st.markdown(f"**Net Value: {trade['net_value']:+.0f}**")
                else:
                    st.warning("No teams have all the players you want, or no fair trades possible.")
        else:
            st.info("Select players you want to receive first!")
