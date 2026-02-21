import { SharedArray } from 'k6/data';

export const users = new SharedArray('users', () => {
  const raw = JSON.parse(open('./config/users_ids_36.json'));
  return raw.users || [];
});

export const location = new SharedArray('location', () => {
  const raw = JSON.parse(open('./config/location.json'));
  return [raw];
})[0];
