import { Request, Response } from 'express';
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET || 'lpr-system-secret-key-2024';
const JWT_EXPIRES_IN = '24h';

// Hardcoded admin user for demo
const ADMIN_USER = {
  id: 1,
  username: 'admin',
  password: 'admin',
  displayName: 'Administrator',
  role: 'admin'
};

export const login = async (req: Request, res: Response) => {
  try {
    const { username, password } = req.body;

    if (!username || !password) {
      return res.status(400).json({
        success: false,
        message: 'Username and password are required'
      });
    }

    // Validate credentials
    if (username !== ADMIN_USER.username || password !== ADMIN_USER.password) {
      return res.status(401).json({
        success: false,
        message: 'Invalid username or password'
      });
    }

    // Generate JWT token
    const token = jwt.sign(
      {
        id: ADMIN_USER.id,
        username: ADMIN_USER.username,
        displayName: ADMIN_USER.displayName,
        role: ADMIN_USER.role
      },
      JWT_SECRET,
      { expiresIn: JWT_EXPIRES_IN }
    );

    return res.json({
      success: true,
      data: {
        token,
        user: {
          id: ADMIN_USER.id,
          username: ADMIN_USER.username,
          displayName: ADMIN_USER.displayName,
          role: ADMIN_USER.role
        }
      }
    });
  } catch (error) {
    console.error('Login error:', error);
    return res.status(500).json({
      success: false,
      message: 'Internal server error'
    });
  }
};

export const getMe = async (req: Request, res: Response) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({
        success: false,
        message: 'No token provided'
      });
    }

    const token = authHeader.split(' ')[1];
    if (!token) {
      return res.status(401).json({
        success: false,
        message: 'Invalid token format'
      });
    }
    const decoded = jwt.verify(token, JWT_SECRET) as any;

    return res.json({
      success: true,
      data: {
        id: decoded.id,
        username: decoded.username,
        displayName: decoded.displayName,
        role: decoded.role
      }
    });
  } catch (error) {
    return res.status(401).json({
      success: false,
      message: 'Invalid or expired token'
    });
  }
};
// reload 2
