import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  withCredentials: true, // send httpOnly cookie on every request
})

// Redirect to login on 401
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
