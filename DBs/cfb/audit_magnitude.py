import pandas as pd
b = pd.read_csv('before_audit_ratings.csv'); a = pd.read_csv('after_audit_ratings.csv')
key = [c for c in ('variant', 'season', 'game_id', 'team') if c in b.columns]
print('merge key:', key)
m = b.merge(a, on=key, suffixes=('_b', '_a'))
print('rows matched:', len(m), 'of', len(b), '/', len(a))
m['d'] = (m['post_rate_a'] - m['post_rate_b']).abs()
if 'season' in key:
    print('max change, seasons before 1999:', m[m.season < 1999]['d'].max(), '(should be 0)')
print('max change:', round(m['d'].max(), 2), ' mean over changed rows:', round(m[m.d > 0]['d'].mean(), 3))
print(m.sort_values('d', ascending=False).head(10)[key + ['d']].to_string(index=False))