from redis import Redis

r = Redis(host="localhost")
r.set('test', 'hello')
print(r.get('test'))