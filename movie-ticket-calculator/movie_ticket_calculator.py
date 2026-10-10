ticket_price = float(input('Ticket price: '))
num_tickets = int(input('Number of tickets: '))
popcorn_price = float(input('Price of popcorn: '))
drinks_price = float(input('Price of drinks: '))
is_member = input("Member? (y/n): ") == "y"
budget = float(input('Total budget: '))
total_cost = (ticket_price * num_tickets) + popcorn_price + drinks_price

if is_member:
     print('You get a discount')
     total_cost = total_cost * 0.90
else: print('You do not get a discount')

if total_cost > budget:
    print(f'You are over budget by ${round(total_cost - budget, 2)}')
else:
    print(f'You are within budget by: ${round(budget - total_cost, 2)}')
